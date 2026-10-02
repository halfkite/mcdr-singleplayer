package io.github.mcdrsingleplayer;

import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.ClientCommands;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.message.v1.ServerMessageEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.commands.CommandSource;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.storage.LevelResource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SingleplayerBridge implements ModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("mcdr_singleplayer_bridge");
    private volatile BridgeEndpoint endpoint;
    private volatile MinecraftServer worldServer;
    private BridgeConfig config;
    private AutoRuntime runtime;
    private Path configPath;
    private RestoreProgressMonitor restoreProgress;
    private final ClientCommandTree clientCommands = new ClientCommandTree(() -> endpoint, this::forward);
    private final Map<ServerLevel, Boolean> previousAutoSave = new HashMap<>();
    private volatile boolean restoreAutoSaveNeeded;
    private java.util.function.Consumer<Runnable> closeDispatcher = action -> Minecraft.getInstance().execute(action);

    void setTestCloseDispatcher(java.util.function.Consumer<Runnable> dispatcher) {
        closeDispatcher = dispatcher == null ? action -> Minecraft.getInstance().execute(action) : dispatcher;
    }

    @Override
    public void onInitialize() {
        configPath = BridgeConfig.pathForGame(FabricLoader.getInstance().getGameDir());
        try {
            config = BridgeConfig.loadForGame(FabricLoader.getInstance().getGameDir());
            if (FabricLoader.getInstance().isModLoaded("singleplayer_bridge_gametest")) {
                // The test instance must not compete with the user's running game/server.
                try (var listener = new java.net.ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1"))) {
                    config.port = listener.getLocalPort();
                }
                java.nio.file.Files.writeString(configPath, new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(config));
            }
        } catch (Exception e) {
            LOGGER.error("MCDR bridge configuration could not be loaded; bridge disabled ({})", e.getClass().getSimpleName());
            Path legacyStatus = FabricLoader.getInstance().getGameDir().resolve("config/.mcdr_restore_progress.json");
            monitorRestore(java.nio.file.Files.isRegularFile(legacyStatus) ? legacyStatus : BridgeConfig.runtimeForGame(FabricLoader.getInstance().getGameDir()).resolve(".mcdr_restore_progress.json"));
            return;
        }
        monitorRestore(BridgeConfig.runtimeForGame(FabricLoader.getInstance().getGameDir()).resolve(".mcdr_restore_progress.json"));
        if (!config.enabled) return;
        if (config.autoStartMcdr && !FabricLoader.getInstance().isModLoaded("singleplayer_bridge_gametest")) {
            runtime = new AutoRuntime(config, configPath, FabricLoader.getInstance().getGameDir());
            ClientLifecycleEvents.CLIENT_STARTED.register(client -> runtime.start());
            ClientLifecycleEvents.CLIENT_STOPPING.register(client -> runtime.closing());
        }
        registerClientCommands();
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            if (server.isDedicatedServer()) return;
            worldServer = server;
            try {
                endpoint = new BridgeEndpoint(config.port, config.token, server.getServerVersion(),
                        server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize().toString(),
                        request -> route(server, request));
                server.getPlayerList().getPlayers().forEach(player -> endpoint.playerJoined(player.getPlainTextName()));
                var client = Minecraft.getInstance();
                endpoint.hostPlayer = client.getUser().getName();
                endpoint.language = client.getLanguageManager().getSelected();
                endpoint.progressPath = BridgeConfig.runtimeForGame(FabricLoader.getInstance().getGameDir()).resolve(".mcdr_restore_progress.json").toAbsolutePath().toString();
                restoreProgress.session(endpoint.session);
                if (runtime != null) runtime.publish(server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize().toString(),
                        endpoint.session, endpoint.hostPlayer, endpoint.language);
                LOGGER.info("MCDR bridge listening at 127.0.0.1:{} for this world", config.port);
            } catch (Exception e) {
                LOGGER.error("MCDR bridge could not open the local port ({})", e.getClass().getSimpleName());
            }
        });
        // End the control session only after world saving and server shutdown have completed.
        ServerLifecycleEvents.SERVER_STOPPED.register(server -> {
            if (server != worldServer) return;
            BridgeEndpoint old = endpoint;
            endpoint = null;
            worldServer = null;
            previousAutoSave.clear();
            restoreAutoSaveNeeded = false;
            if (old != null) old.close();
            if (runtime != null) runtime.publish(null, null);
        });
        ServerPlayConnectionEvents.JOIN.register((listener, sender, server) -> {
            BridgeEndpoint bridge = endpoint;
            if (bridge != null && server == worldServer) bridge.playerJoined(listener.player.getPlainTextName());
        });
        ServerPlayConnectionEvents.DISCONNECT.register((listener, server) -> {
            BridgeEndpoint bridge = endpoint;
            if (bridge != null && server == worldServer) bridge.playerLeft(listener.player.getPlainTextName());
        });
        ServerMessageEvents.CHAT_MESSAGE.register((message, player, chatType) -> {
            BridgeEndpoint bridge = endpoint;
            if (bridge != null && player.level().getServer() == worldServer) {
                var event = bridge.event("chat");
                event.addProperty("player", player.getPlainTextName());
                event.addProperty("text", message.signedContent());
                bridge.publish(event);
            }
        });
        ServerMessageEvents.GAME_MESSAGE.register((server, message, overlay) -> {
            BridgeEndpoint bridge = endpoint;
            if (bridge != null && server == worldServer) {
                var event = bridge.event("log");
                String text = message.getString();
                event.addProperty("text", text.length() > 8000 ? text.substring(0, 8000) : text);
                bridge.publish(event);
            }
        });
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            clientCommands.tick();
            BridgeEndpoint bridge = endpoint;
            if (bridge != null) {
                bridge.pause(client.isPaused());
                MinecraftServer server = worldServer;
                if (restoreAutoSaveNeeded && !bridge.connected() && server != null) server.execute(() -> {
                    if (endpoint == bridge && !bridge.connected()) restoreAutoSave(server);
                });
            }
        });
    }

    private void monitorRestore(Path progressPath) {
        // Even failed/deferred configuration migration must keep unfinished worlds locked.
        restoreProgress = new RestoreProgressMonitor(progressPath,
                BridgeConfig.runtimeForGame(FabricLoader.getInstance().getGameDir()));
        RestoreTitleOverlay.register(restoreProgress);
        ClientLifecycleEvents.CLIENT_STOPPING.register(client -> restoreProgress.close());
    }

    // The client integration fixture uses an isolated installation without touching the user's MCDR.
    void enableTestAutomation(Path common, String python) {
        config.pythonExecutable = python;
        runtime = new AutoRuntime(config, configPath, FabricLoader.getInstance().getGameDir());
        runtime.start();
    }

    private void registerClientCommands() {
        ClientCommandRegistrationCallback.EVENT.register((dispatcher, context) -> {
            clientCommands.attach(dispatcher);
            dispatcher.register(ClientCommands.literal("mcdr_setup").requires(FabricClientCommandSource::attended)
                    .then(ClientCommands.literal("recommend").executes(command -> setup(command.getSource(), "recommend")))
                    .then(ClientCommands.literal("owner").executes(command -> setup(command.getSource(), "owner"))));
        });
    }

    private int forward(FabricClientCommandSource source, String command) {
        BridgeEndpoint bridge = endpoint;
        if (bridge == null || !bridge.clientChat(source.getPlayer().getPlainTextName(), command)) {
            source.sendError(Component.literal("MCDR 尚未连接当前单人存档，请查看 mcdr-singleplayer/log/bootstrap.log。"));
            return 0;
        }
        return 1;
    }

    private int setup(FabricClientCommandSource source, String action) {
        if (runtime == null || worldServer == null || endpoint == null) {
            source.sendError(Component.literal("请启用游戏自动启动模式并进入单人存档。"));
            return 0;
        }
        runtime.requestSetup(action, source.getPlayer().getPlainTextName());
            source.sendFeedback(Component.literal("已提交 MCDR 设置请求；完成结果见 mcdr-singleplayer/log/存档名/controller-child.log。"));
        return 1;
    }

    private void route(MinecraftServer server, BridgeEndpoint.Request request) {
        if (BridgeEndpoint.SAVE_AND_QUIT.equals(request.command)) {
            closeDispatcher.accept(() -> {
                var client = Minecraft.getInstance();
                if (server != worldServer || client.getSingleplayerServer() != server || !request.valid()) {
                    request.complete(false, "World close cancelled: world changed or connection lost");
                    return;
                }
                request.complete(true, "Saving and closing the singleplayer world");
                restoreProgress.closingWorld(server.getWorldPath(LevelResource.ROOT).toAbsolutePath().toString(), endpoint.session);
                client.disconnectFromWorld(Component.literal("Prime Backup restore"));
                client.gui.setScreen(new net.minecraft.client.gui.screens.TitleScreen());
            });
        } else server.execute(() -> execute(server, request));
    }

    private void restoreAutoSave(MinecraftServer server) {
        if (server != worldServer) return;
        previousAutoSave.forEach((level, noSave) -> level.noSave = noSave);
        previousAutoSave.clear();
        restoreAutoSaveNeeded = false;
    }

    private void execute(MinecraftServer server, BridgeEndpoint.Request request) {
        if (server != worldServer || !request.valid() || server.isStopped() || server.isPaused()) {
            request.complete(false, "Command discarded: world changed, paused, disconnected or deadline expired");
            return;
        }
        String command = request.command.strip();
        if (command.startsWith("/")) command = command.substring(1);
        if (command.isBlank() || command.indexOf('\n') >= 0 || command.indexOf('\r') >= 0) {
            request.complete(false, "Command rejected: empty or multiline input");
            return;
        }
        if (command.equals("stop") || command.startsWith("stop ")) {
            request.complete(false, "World shutdown is not supported; use Save and Quit in Minecraft");
            return;
        }
        Capture capture = new Capture();
        try {
            // These dedicated-server commands are absent from the integrated dispatcher.
            // Invoke the same game save APIs and only acknowledge after flush has finished.
            if (command.equals("save-off")) {
                for (ServerLevel level : server.getAllLevels()) previousAutoSave.putIfAbsent(level, level.noSave);
                server.setAutoSave(false);
                restoreAutoSaveNeeded = true;
                request.complete(true, "Automatic saving is now disabled");
                return;
            }
            if (command.equals("save-on")) {
                server.setAutoSave(true);
                previousAutoSave.clear();
                restoreAutoSaveNeeded = false;
                request.complete(true, "Automatic saving is now enabled");
                return;
            }
            if (command.equals("save-all") || command.equals("save-all flush")) {
                boolean success = server.saveEverything(true, command.endsWith(" flush"), true);
                request.complete(success, success ? "Saved the game" : "World save failed");
                return;
            }
            var source = server.createCommandSourceStack().withSource(capture)
                    .withCallback((success, result) -> { capture.success |= success; capture.result += result; });
            server.getCommands().performPrefixedCommand(source, command);
            String output = capture.text.length() == 0 ? "Command completed (result " + capture.result + ")" : capture.text.toString();
            request.complete(capture.success, output);
        } catch (RuntimeException e) {
            request.complete(false, "Command execution failed (" + e.getClass().getSimpleName() + ")");
        }
    }

    private static final class Capture implements CommandSource {
        final StringBuilder text = new StringBuilder();
        boolean success;
        int result;

        @Override public void sendSystemMessage(Component message) {
            if (text.length() >= 8000) return;
            if (text.length() > 0) text.append('\n');
            String output = message.getString();
            text.append(output, 0, Math.min(output.length(), 8000 - text.length()));
        }
        @Override public boolean acceptsSuccess() { return true; }
        @Override public boolean acceptsFailure() { return true; }
        @Override public boolean shouldInformAdmins() { return false; }
    }
}
