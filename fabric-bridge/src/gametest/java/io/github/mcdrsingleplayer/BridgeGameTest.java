package io.github.mcdrsingleplayer;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.TimeUnit;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.loader.api.FabricLoader;

/** Exercises the installed main mod in a real, separate singleplayer test world. */
public final class BridgeGameTest implements FabricClientGameTest {
    static SingleplayerBridge mainBridge() {
        return FabricLoader.getInstance().getEntrypointContainers("main", net.fabricmc.api.ModInitializer.class).stream()
            .map(entry -> entry.getEntrypoint()).filter(entry -> entry instanceof SingleplayerBridge)
            .map(entry -> (SingleplayerBridge) entry).findFirst().orElseThrow();
    }

    static void awaitAsyncClose(ClientGameTestContext context, java.util.Queue<Runnable> tasks,
            java.util.function.Predicate<net.minecraft.client.Minecraft> predicate, int ticks) {
        // Fabric 26.3 gametests gate server ticks. Dispatch an external close inside its
        // controlled client phase so IntegratedServer.halt can finish its blocking work.
        context.waitFor(client -> {
            Runnable action;
            while ((action = tasks.poll()) != null) action.run();
            return predicate.test(client);
        }, ticks);
        // Fabric defers disconnect inside PHASE_TEST, which runs after vanilla's
        // disconnectFromWorld has already selected TitleScreen. Its deferred call
        // leaves the saving screen. Match TestSingleplayerContextImpl.close here.
        context.waitFor(client -> client.level == null && client.player == null, 100);
        context.waitTicks(2);
        context.setScreen(net.minecraft.client.gui.screens.TitleScreen::new);
        context.waitTicks(2);
    }
    @Override
    public void runTest(ClientGameTestContext context) {
        AtomicBoolean received = new AtomicBoolean();
        ClientReceiveMessageEvents.GAME.register((message, overlay) -> {
            if ("bridge-game-test".equals(message.getString())) received.set(true);
        });
        try {
            BridgeConfig config = BridgeConfig.load(BridgeConfig.pathForGame(FabricLoader.getInstance().getGameDir()));
            String session;
            var firstWorld = context.worldBuilder().create();
            try (var socket = new TestSocket(config)) {
                try {
                JsonObject ready = socket.await(context, "ready", null);
                session = ready.get("session").getAsString();
                check("26.3".equals(ready.get("game_version").getAsString()), "Wrong game version");
                check(ready.getAsJsonArray("players").size() == 1, "Missing player snapshot");
                socket.command(session, "list-test", "list");
                var listed = socket.await(context, "command_result", "list-test");
                check(listed.get("success").getAsBoolean(), "List command failed: " + listed);
                socket.command(session, "message-test", "tellraw @a \"bridge-game-test\"");
                check(socket.await(context, "command_result", "message-test").get("success").getAsBoolean(), "tellraw failed");
                context.waitFor(client -> received.get());
                context.runOnClient(client -> client.player.connection.sendChat("!!bridge-game-test"));
                var chat = socket.await(context, "chat", null);
                check("!!bridge-game-test".equals(chat.get("text").getAsString()), "Chat text changed");
                check(chat.get("player").getAsString().equals(ready.getAsJsonArray("players").get(0).getAsString()), "Chat identity changed");
                socket.command("old-session", "stale-test", "say must-not-run");
                check(!socket.await(context, "command_result", "stale-test").get("success").getAsBoolean(), "Stale command executed");
                socket.command(session, "invalid-test", "this_command_does_not_exist");
                check(!socket.await(context, "command_result", "invalid-test").get("success").getAsBoolean(), "Invalid command reported success");
                context.runOnClient(client -> client.pauseGame(false));
                context.waitFor(client -> client.isPaused());
                socket.await(context, "pause", null);
                socket.command(session, "pause-test", "say must-not-run");
                check(!socket.await(context, "command_result", "pause-test").get("success").getAsBoolean(), "Paused command executed");
                context.runOnClient(client -> client.gui.setScreen(null));
                context.waitFor(client -> !client.isPaused());
                context.takeScreenshot("singleplayer-bridge-connected");
                } finally {
                    firstWorld.close();
                }
                socket.await(context, "world_stopped", null);
            }
            try (var world = context.worldBuilder().create(); var socket = new TestSocket(config)) {
                var ready = socket.await(context, "ready", null);
                check(!session.equals(ready.get("session").getAsString()), "New world reused session identifier");
                socket.command(session, "cross-world-test", "say must-not-run");
                check(!socket.await(context, "command_result", "cross-world-test").get("success").getAsBoolean(), "Old-world command accepted");
                socket.command(ready.get("session").getAsString(), "save-off-detach-test", "save-off");
                check(socket.await(context, "command_result", "save-off-detach-test").get("success").getAsBoolean(), "save-off failed");
                check(world.getServer().computeOnServer(server -> !server.isAutoSave()), "save-off did not disable saving");
                socket.close();
                world.getServer().waitFor(server -> server.isAutoSave());
            }
            String python = System.getenv("MCDR_BRIDGE_TEST_PYTHON");
            String project = System.getenv("MCDR_BRIDGE_TEST_ROOT");
            if (python != null && project != null) testFullMcdrPath(context, python, Path.of(project));
        } catch (IOException e) {
            throw new AssertionError("Bridge game test transport failed", e);
        }
    }

    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private void testFullMcdrPath(ClientGameTestContext context, String python, Path project) throws IOException {
        AtomicBoolean reply = new AtomicBoolean();
        ClientReceiveMessageEvents.GAME.register((message, overlay) -> {
            if ("full-path-ok".equals(message.getString())) reply.set(true);
        });
        try (var world = context.worldBuilder().create()) {
            Path gameDir = FabricLoader.getInstance().getGameDir().toAbsolutePath();
            Path log = gameDir.resolve("mcdr-full-path.log");
            String player = context.computeOnClient(client -> client.player.getPlainTextName());
            Process mcdr = new ProcessBuilder(python, project.resolve("scripts/game_mcdr_harness.py").toString(),
                    "--game-dir", gameDir.toString(), "--player", player)
                    .redirectErrorStream(true).redirectOutput(log.toFile()).start();
            try {
                context.waitFor(client -> {
                    try { return Files.exists(log) && Files.readString(log).contains("Singleplayer world ready"); }
                    catch (IOException e) { return false; }
                }, 1200);
                context.runOnClient(client -> client.player.connection.sendChat("!!fullbridge"));
                context.waitFor(client -> reply.get(), 800);
                context.takeScreenshot("singleplayer-bridge-mcdr-full-path");
                mcdr.getOutputStream().write("!!MCDR server stop_exit\n".getBytes(StandardCharsets.UTF_8));
                mcdr.getOutputStream().flush();
                context.waitFor(client -> !mcdr.isAlive(), 800);
                check(mcdr.exitValue() == 0, "MCDR exit failed; see " + log);
                check(context.computeOnClient(client -> client.level != null), "Detaching MCDR exited the world");
            } finally {
                if (mcdr.isAlive()) {
                    mcdr.destroy();
                    try {
                        if (!mcdr.waitFor(5, TimeUnit.SECONDS)) mcdr.destroyForcibly();
                    } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                }
            }
        }
    }

    private static final class TestSocket implements AutoCloseable {
        final Socket socket;
        final LinkedBlockingQueue<JsonObject> events = new LinkedBlockingQueue<>();

        TestSocket(BridgeConfig config) throws IOException {
            socket = new Socket("127.0.0.1", config.port);
            JsonObject hello = new JsonObject();
            hello.addProperty("type", "hello");
            hello.addProperty("protocol", 1);
            hello.addProperty("token", config.token);
            send(hello);
            Thread.ofVirtual().start(() -> {
                try {
                    while (!socket.isClosed()) events.add(BridgeEndpoint.readFrame(socket.getInputStream()));
                } catch (IOException ignored) { }
            });
        }

        void send(JsonObject frame) throws IOException {
            socket.getOutputStream().write((frame + "\n").getBytes(StandardCharsets.UTF_8));
            socket.getOutputStream().flush();
        }

        void command(String session, String id, String command) throws IOException {
            JsonObject frame = new JsonObject();
            frame.addProperty("type", "command");
            frame.addProperty("session", session);
            frame.addProperty("id", id);
            frame.addProperty("command", command);
            frame.addProperty("deadline", System.currentTimeMillis() + 10000);
            send(frame);
        }

        JsonObject await(ClientGameTestContext context, String type, String id) {
            context.waitFor(client -> events.stream().anyMatch(event -> matches(event, type, id)), 400);
            JsonObject event = events.stream().filter(value -> matches(value, type, id)).findFirst().orElseThrow();
            events.remove(event);
            return event;
        }

        boolean matches(JsonObject event, String type, String id) {
            return type.equals(event.get("type").getAsString()) && (id == null || id.equals(event.get("id").getAsString()));
        }

        @Override public void close() throws IOException { socket.close(); }
    }
}
