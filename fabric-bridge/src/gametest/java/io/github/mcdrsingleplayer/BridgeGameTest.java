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
        if (MultiClientGameTest.selected()) return;
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
                socket.command(session, "short-name-query", "__bridge_player_data__ 1");
                var missingBot = socket.await(context, "command_result", "short-name-query");
                String missingPlayerMessage = context.computeOnClient(client -> net.minecraft.network.chat.Component.translatable(
                        "mcdr-singleplayer.error.player_is_no_longer_in_this_world").getString());
                check(!missingBot.get("success").getAsBoolean() && missingPlayerMessage.equals(missingBot.get("text").getAsString()),
                        "The player position route still rejects short names: " + missingBot);
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
                testLanCommandRoute(context, firstWorld.getServer(), socket, session);
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

    private static BridgeEndpoint mainEndpoint() {
        try {
            var field = SingleplayerBridge.class.getDeclaredField("endpoint");
            field.setAccessible(true);
            return (BridgeEndpoint) field.get(mainBridge());
        } catch (ReflectiveOperationException e) { throw new AssertionError(e); }
    }

    private void testLanCommandRoute(ClientGameTestContext context,
            net.fabricmc.fabric.api.client.gametest.v1.context.TestServerContext serverContext,
            TestSocket socket, String session) throws IOException {
        // Exercise the vanilla server dispatcher and command packet path, rather than
        // the host-only Fabric client command dispatcher. The guest is a synthetic
        // ServerPlayer; this does not substitute for a second-client LAN smoke test.
        var graph = com.google.gson.JsonParser.parseString("""
            {"roots":[0,3],"nodes":[
              {"kind":"literal","name":"!!lanbridge","children":[1],"redirect":null},
              {"kind":"literal","name":"nested","children":[2],"redirect":null},
              {"kind":"argument","name":"value","greedy":false,"children":[],"redirect":null},
              {"kind":"literal","name":"list","children":[],"redirect":null}]}
            """).getAsJsonObject();
        socket.tree(session, graph);
        serverContext.waitFor(server -> server.getCommands().getDispatcher().getRoot().getChild("!!lanbridge") != null);
        context.waitFor(client -> client.getConnection().getCommands().getRoot().getChild("!!lanbridge") != null);
        check(context.computeOnClient(client -> client.getConnection().getCommands().getRoot().getChild("!!lanbridge").getChild("nested")
                .getChildren().stream().filter(node -> node instanceof com.mojang.brigadier.tree.ArgumentCommandNode<?, ?> argument
                    && argument.getCustomSuggestions() != null).count() == 1), "LAN graph sends competing remote suggestion requests");
        serverContext.runOnServer(server -> server.getCommands().performPrefixedCommand(
                server.getPlayerList().getPlayers().getFirst().createCommandSourceStack(), "!!lanbridge nested host"));
        var host = socket.await(context, "chat", null);
        check(host.get("text").getAsString().equals("!!lanbridge nested host"), "Server host command was not forwarded");

        BridgeEndpoint bridge = mainEndpoint();
        var guest = serverContext.computeOnServer(server -> new net.minecraft.server.level.ServerPlayer(
                server, server.overworld(), new com.mojang.authlib.GameProfile(java.util.UUID.randomUUID(), "LanGuest"),
                net.minecraft.server.level.ClientInformation.createDefault()));
        bridge.playerJoined("LanGuest");
        try {
            serverContext.runOnServer(server -> server.getCommands().performPrefixedCommand(
                    guest.createCommandSourceStack(), "!!lanbridge nested guest"));
            var forwarded = socket.await(context, "chat", null);
            check(forwarded.get("player").getAsString().equals("LanGuest"), "Guest command used the host identity");
            check(forwarded.get("text").getAsString().equals("!!lanbridge nested guest"), "Guest command changed");
            var completion = serverContext.computeOnServer(server -> {
                var dispatcher = server.getCommands().getDispatcher();
                return dispatcher.getCompletionSuggestions(dispatcher.parse("!!lanbridge nested g", guest.createCommandSourceStack()));
            });
            var requested = socket.await(context, "suggest_request", null);
            check(requested.get("player").getAsString().equals("LanGuest"), "Guest completion used the host identity");
            var response = new JsonObject();
            response.addProperty("type", "suggest_result");
            response.addProperty("session", session);
            response.addProperty("id", requested.get("id").getAsString());
            response.add("suggestions", com.google.gson.JsonParser.parseString("[\"!!lanbridge nested guest\"]"));
            socket.send(response);
            context.waitFor(client -> completion.isDone());
            check(completion.join().getList().stream().anyMatch(value -> value.getText().contains("guest")), "Guest completion missing");
        } finally { bridge.playerLeft("LanGuest"); }
        socket.tree(session, com.google.gson.JsonParser.parseString("{\"roots\":[],\"nodes\":[]}").getAsJsonObject());
        serverContext.waitFor(server -> server.getCommands().getDispatcher().getRoot().getChild("!!lanbridge") == null);
        context.waitFor(client -> client.getConnection().getCommands().getRoot().getChild("!!lanbridge") == null);
        check(serverContext.computeOnServer(server -> server.getCommands().getDispatcher().getRoot().getChild("list") != null),
                "Unloading MCDR commands removed a vanilla root");
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
            BridgeEndpoint bridge = mainEndpoint();
            // Match the ready snapshot produced by a Carpet world containing bot "1".
            // The test registers its presence in the actual transport, without Carpet.
            bridge.playerJoined("1");
            Process mcdr = new ProcessBuilder(python, project.resolve("scripts/game_mcdr_harness.py").toString(),
                    "--game-dir", gameDir.toString(), "--player", player)
                    .redirectErrorStream(true).redirectOutput(log.toFile()).start();
            try {
                context.waitFor(client -> {
                    try { return Files.exists(log) && Files.readString(log).contains("Singleplayer world ready"); }
                    catch (IOException e) { return false; }
                }, 1200);
                context.waitFor(client -> {
                    try { return Files.readString(log).contains("1 joined the singleplayer world"); }
                    catch (IOException e) { return false; }
                }, 800);
                bridge.playerJoined("ab");
                bridge.playerLeft("ab");
                context.waitFor(client -> {
                    try { return Files.readString(log).contains("ab left the singleplayer world"); }
                    catch (IOException e) { return false; }
                }, 800);
                context.runOnClient(client -> client.player.connection.sendChat("!!fullbridge"));
                context.waitFor(client -> reply.get(), 800);
                context.takeScreenshot("singleplayer-bridge-mcdr-full-path");
                mcdr.getOutputStream().write("!!MCDR server stop_exit\n".getBytes(StandardCharsets.UTF_8));
                mcdr.getOutputStream().flush();
                context.waitFor(client -> !mcdr.isAlive(), 800);
                check(mcdr.exitValue() == 0, "MCDR exit failed; see " + log);
                check(context.computeOnClient(client -> client.level != null), "Detaching MCDR exited the world");
            } finally {
                bridge.playerLeft("1");
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

        void tree(String session, JsonObject graph) throws IOException {
            JsonObject frame = new JsonObject();
            frame.addProperty("type", "command_tree");
            frame.addProperty("session", session);
            frame.addProperty("revision", java.util.UUID.randomUUID().toString());
            frame.addProperty("total", 1);
            frame.addProperty("index", 0);
            frame.addProperty("payload", graph.toString());
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
