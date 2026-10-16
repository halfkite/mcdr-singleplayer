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
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.message.v1.ServerMessageEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.commands.CommandSource;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.ChatFormatting;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SingleplayerBridge implements ModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("mcdr_singleplayer_bridge");
    /** The mod entrypoint, so the title screen widget can read this launch's setup state. */
    private static volatile SingleplayerBridge INSTANCE;
    /** Fallback for the bundled materials folder; matches gradle.properties and is release-checked. */
    private static final String BUNDLED_VERSION = "0.6.0";
    private volatile BridgeEndpoint endpoint;
    private volatile MinecraftServer worldServer;
    private BridgeConfig config;
    private AutoRuntime runtime;
    private Path configPath;
    private RestoreProgressMonitor restoreProgress;
    private boolean showingPythonPrompt;
    private boolean pythonPromptDismissed;
    private InstallProgress.Feedback installFeedback = new InstallProgress.Feedback();
    private boolean mcdrSetupPromptShown;
    private boolean mcdrSetupPromptDismissed;
    private boolean mcdrNoticeAnnounced;
    private int setupCheckTicks;
    /** The title screen entry of the current screen, refreshed while it is shown. */
    private MenuIconButton menuButton;
    private final ClientCommandTree clientCommands = new ClientCommandTree(() -> endpoint, this::forward);
    private final ServerCommandTree serverCommands = new ServerCommandTree(() -> endpoint);
    private final Map<ServerLevel, Boolean> previousAutoSave = new HashMap<>();
    private volatile boolean restoreAutoSaveNeeded;
    private java.util.function.Consumer<Runnable> closeDispatcher = action -> Minecraft.getInstance().execute(action);

    void setTestCloseDispatcher(java.util.function.Consumer<Runnable> dispatcher) {
        closeDispatcher = dispatcher == null ? action -> Minecraft.getInstance().execute(action) : dispatcher;
    }

    @Override
    public void onInitialize() {
        INSTANCE = this;
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
            runtime = new AutoRuntime(config, configPath, FabricLoader.getInstance().getGameDir(), modVersion());
            ClientLifecycleEvents.CLIENT_STARTED.register(client -> runtime.start());
            ClientLifecycleEvents.CLIENT_STOPPING.register(client -> runtime.closing());
        }
        if (!FabricLoader.getInstance().isModLoaded("singleplayer_bridge_gametest")) registerMenuButton();
        registerClientCommands();
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            if (server.isDedicatedServer()) return;
            worldServer = server;
            try {
                endpoint = new BridgeEndpoint(runtime != null ? 0 : config.port, config.token, server.getServerVersion(),
                        server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize().toString(),
                        request -> route(server, request));
                server.getPlayerList().getPlayers().forEach(player -> endpoint.playerJoined(player.getPlainTextName()));
                var client = Minecraft.getInstance();
                endpoint.hostPlayer = client.getUser().getName();
                endpoint.language = client.getLanguageManager().getSelected();
                endpoint.progressPath = BridgeConfig.runtimeForGame(FabricLoader.getInstance().getGameDir()).resolve(".mcdr_restore_progress.json").toAbsolutePath().toString();
                restoreProgress.session(endpoint.session);
                if (runtime != null) runtime.publish(server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize().toString(),
                        endpoint.session, endpoint.hostPlayer, endpoint.language, endpoint.port());
                serverCommands.attach(server);
                LOGGER.info("MCDR bridge listening at 127.0.0.1:{} for this world", endpoint.port());
            } catch (Exception e) {
                LOGGER.error("MCDR bridge could not open the local port ({})", e.getClass().getSimpleName());
            }
        });
        ServerTickEvents.END_SERVER_TICK.register(serverCommands::tick);
        // End the control session only after world saving and server shutdown have completed.
        ServerLifecycleEvents.SERVER_STOPPED.register(server -> {
            if (server != worldServer) return;
            BridgeEndpoint old = endpoint;
            endpoint = null;
            worldServer = null;
            previousAutoSave.clear();
            restoreAutoSaveNeeded = false;
            if (old != null) old.close();
            serverCommands.stop();
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
            if (menuButton != null) menuButton.refresh();
            if (runtime != null) {
                boolean inSingleplayer = inSingleplayer(client);
                if (runtime.pythonMissing() && inSingleplayer) {
                    if (!showingPythonPrompt && !pythonPromptDismissed) {
                        showingPythonPrompt = true;
                        client.gui.setScreen(new PythonSetupScreen(() -> {
                            showingPythonPrompt = false;
                            pythonPromptDismissed = true;
                        }));
                    }
                } else if (!inSingleplayer) {
                    if ((showingPythonPrompt && client.gui.screen() instanceof PythonSetupScreen)) client.gui.setScreen(null);
                    showingPythonPrompt = false;
                    pythonPromptDismissed = false;
                    installFeedback = new InstallProgress.Feedback();
                    // A new visit to the menu may announce the missing runtime once more.
                    mcdrNoticeAnnounced = false;
                    pollMcdrSetup(client);
                    if (!mcdrSetupPromptDismissed) maybeOpenMcdrSetupPrompt(client);
                } else if (runtime.pythonReady()) {
                    InstallProgress value = currentInstallProgress();
                    // Only real installation work is narrated; a running controller must stay quiet.
                    if (installFeedback.shouldAnnounceInstallation(value, System.currentTimeMillis())) {
                        Component stage = Component.translatable(value.translationKey());
                        if (value.attempt() > 0) stage = stage.copy().append(Component.translatable(
                                "mcdr-singleplayer.install.attempt", value.attempt()));
                        client.player.sendSystemMessage(Component.translatable("mcdr-singleplayer.install.chat", stage));
                    }
                    if (!mcdrNoticeAnnounced && runtime.setupStatus() != null
                            && !runtime.setupStatus().running() && !value.running()) {
                        mcdrNoticeAnnounced = true;
                        client.player.sendSystemMessage(Component.translatable("mcdr-singleplayer.setup.menu_hint"));
                    }
                }
            }
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

    private InstallProgress currentInstallProgress() {
        return runtime.installProgress(false);
    }

    private static boolean inSingleplayer(Minecraft client) {
        return client.getSingleplayerServer() != null && client.player != null && client.level != null;
    }

    /** Refresh the published setup reason while the player is at the menu. */
    private void pollMcdrSetup(Minecraft client) {
        McdrSetup setup = runtime.setupStatus();
        if (setup == null) return;
        if (--setupCheckTicks <= 0) {
            setupCheckTicks = 20;
            if (client.gui.screen() instanceof TitleScreen) setup.write();
        }
    }

    /** One dismissible prompt per launch; the menu button reopens the same information later. */
    private void maybeOpenMcdrSetupPrompt(Minecraft client) {
        if (mcdrSetupPromptShown) return;
        if (!(client.gui.screen() instanceof TitleScreen)) return;
        if (client.getSingleplayerServer() != null) return;
        McdrSetup setup = runtime.setupStatus();
        if (setup != null && setup.actionNeeded() && !setup.reason().isEmpty()) {
            mcdrSetupPromptShown = true;
            openMcdrSetup(client, true);
        }
    }

    /**
     * The auto-opened prompt dismisses for the rest of this launch; the manual button only returns
     * to the menu, so reopening it from the menu never hides the download from later visits.
     */
    private void openMcdrSetup(Minecraft client, boolean dismissAfterClose) {
        client.gui.setScreen(new McdrSetupScreen(new McdrSetupScreen.Behaviour() {
            @Override public McdrSetupScreen.View view() { return mcdrSetupView(); }

            @Override public void install() {
                runtime.requestInstall();
                client.gui.setScreen(null);
            }

            @Override public void dismiss() {
                if (dismissAfterClose) mcdrSetupPromptDismissed = true;
            }
        }));
    }

    /**
     * MCDR itself is the only thing the menu offers to install here. This screen prepares the
     * shared runtime, so a finished install moves straight to ready without waiting for a world.
     */
    private McdrSetupScreen.View mcdrSetupView() {
        McdrSetup setup = runtime.setupStatus();
        InstallProgress progress = runtime.installProgress(false);
        return new McdrSetupScreen.View(setupStatus(setup, progress), setup == null ? "" : setup.reason(), progress);
    }

    static McdrSetupScreen.Status setupStatus(McdrSetup setup, InstallProgress progress) {
        if (setup == null) return McdrSetupScreen.Status.CHECKING;
        String reason = setup.reason();
        if (McdrSetup.READY.equals(reason)) return McdrSetupScreen.Status.READY;
        if (setup.running()) {
            if (progress.stage().equals("failed")) return McdrSetupScreen.Status.FAILED;
            // The controller reaches this stage with MCDR fully prepared and waiting for a world.
            return !progress.stage().equals("starting") && !progress.stage().equals("ready")
                    ? McdrSetupScreen.Status.INSTALLING : McdrSetupScreen.Status.READY;
        }
        if (reason.equals("failed")) return McdrSetupScreen.Status.FAILED;
        return reason.isEmpty() ? McdrSetupScreen.Status.CHECKING : McdrSetupScreen.Status.NEEDS_INSTALL;
    }

    /**
     * Menu entry next to the vanilla Mods button. Fabric's screen event runs at the right moment
     * without a mixin, and it replaces any previous screen, so the entry is created here.
     */
    private void registerMenuButton() {
        net.fabricmc.fabric.api.client.screen.v1.ScreenEvents.AFTER_INIT.register((client, screen, width, height) -> {
            if (!(screen instanceof TitleScreen)) return;
            MenuIconButton button = new MenuIconButton(0, 0, 20, 20, pressed -> openMcdrSetup(client, false));
            button.visible = runtime != null;
            net.fabricmc.fabric.api.client.screen.v1.Screens.getWidgets(screen).add(button);
            button.refresh();
            menuButton = button;
            placeMenuButton(button, net.fabricmc.fabric.api.client.screen.v1.Screens.getWidgets(screen),
                    width, height);
        });
    }

    /** Same rules Flashback uses; the entry never lands on top of another mod's button. */
    private static void placeMenuButton(MenuIconButton button, java.util.List<AbstractWidget> widgets,
            int screenWidth, int screenHeight) {
        java.util.List<MenuButtonPlacement.Box> boxes = new java.util.ArrayList<>(widgets.size());
        for (AbstractWidget widget : widgets) {
            boxes.add(new MenuButtonPlacement.Box(widget.getX(), widget.getY(), widget.getWidth(),
                    widget.getHeight(), widget.visible));
        }
        MenuButtonPlacement.Box own = new MenuButtonPlacement.Box(button.getX(), button.getY(), button.getWidth(),
                button.getHeight(), true);
        MenuButtonPlacement.Box replay = null;
        String replayLabel = Component.translatable(MenuButtonPlacement.FLASHBACK_REPLAY_LABEL).getString();
        for (AbstractWidget widget : widgets) {
            if (widget != button && widget.getMessage().getString().startsWith(replayLabel)) {
                replay = new MenuButtonPlacement.Box(widget.getX(), widget.getY(), widget.getWidth(),
                        widget.getHeight(), widget.visible);
                break;
            }
        }
        MenuButtonPlacement.Position position = MenuButtonPlacement.place(boxes, own, replay, screenWidth, screenHeight);
        if (position != null) button.setPosition(position.x(), position.y());
    }

    /** Marks the menu entry while MCDR still needs a download or an update. */
    public static boolean setupNeedsAttention() {
        SingleplayerBridge bridge = INSTANCE;
        return bridge != null && bridge.runtime != null && bridge.runtime.setupStatus() != null
                && bridge.runtime.setupStatus().actionNeeded();
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
        runtime = new AutoRuntime(config, configPath, FabricLoader.getInstance().getGameDir(), modVersion());
        runtime.start();
    }

    /** The jar that ships the installer materials owns their folder name. */
    private static String modVersion() {
        return FabricLoader.getInstance().getModContainer("mcdr-singleplayer")
                .map(container -> container.getMetadata().getVersion().getFriendlyString())
                .filter(version -> !version.isBlank())
                .orElse(BUNDLED_VERSION);
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
            source.sendError(Component.translatable("mcdr-singleplayer.client.no_connection"));
            return 0;
        }
        return 1;
    }

    private int setup(FabricClientCommandSource source, String action) {
        if (runtime == null || worldServer == null || endpoint == null) {
            source.sendError(Component.translatable("mcdr-singleplayer.client.auto_required"));
            return 0;
        }
        runtime.requestSetup(action, source.getPlayer().getPlainTextName());
            source.sendFeedback(Component.translatable("mcdr-singleplayer.client.setup_submitted"));
        return 1;
    }

    private void route(MinecraftServer server, BridgeEndpoint.Request request) {
        if (BridgeEndpoint.SAVE_AND_QUIT.equals(request.command)) {
            closeDispatcher.accept(() -> {
                var client = Minecraft.getInstance();
                if (server != worldServer || client.getSingleplayerServer() != server || !request.valid()) {
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.world_close_cancelled_world_changed_or_connection_lost").getString());
                    return;
                }
                request.complete(true, "Saving and closing the singleplayer world");
                restoreProgress.closingWorld(server.getWorldPath(LevelResource.ROOT).toAbsolutePath().toString(), endpoint.session);
                client.disconnectFromWorld(Component.translatable("mcdr-singleplayer.restore.disconnect"));
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
            request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_discarded_world_changed_paused_disconnected_or_deadline_expired").getString());
            return;
        }
        String command = request.command.strip();
        if (command.startsWith("/")) command = command.substring(1);
        if (command.isBlank() || command.indexOf('\n') >= 0 || command.indexOf('\r') >= 0) {
            request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_rejected_empty_or_multiline_input").getString());
            return;
        }
        if (command.equals("stop") || command.startsWith("stop ")) {
            request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.world_shutdown_is_not_supported_use_save_and_quit_in_minecraft").getString());
            return;
        }
        Capture capture = new Capture();
        try {
            // Read both values in one server tick; plugin adapters need no translated NBT text.
            if (command.startsWith("__bridge_player_data__ ")) {
                String name = command.substring("__bridge_player_data__ ".length());
                if (!name.matches("[A-Za-z0-9_]{1,16}")) {
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.invalid_player_name").getString());
                    return;
                }
                var player = server.getPlayerList().getPlayerByName(name);
                if (player == null) {
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.player_is_no_longer_in_this_world").getString());
                    return;
                }
                var data = new com.google.gson.JsonObject();
                data.addProperty("player", player.getPlainTextName());
                data.addProperty("x", player.getX());
                data.addProperty("y", player.getY());
                data.addProperty("z", player.getZ());
                data.addProperty("dimension", player.level().dimension().identifier().toString());
                request.complete(true, data.toString());
                return;
            }
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
                request.complete(success, success ? "Saved the game" : net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.world_save_failed").getString());
                return;
            }
            command = McdrClickCommandRewriter.addSlash(command);
            var source = server.createCommandSourceStack().withSource(capture)
                    .withCallback((success, result) -> { capture.success |= success; capture.result += result; });
            server.getCommands().performPrefixedCommand(source, command);
            String output = capture.text.length() == 0 ? "Command completed (result " + capture.result + ")" : capture.text.toString();
            request.complete(capture.success, output);
        } catch (RuntimeException e) {
            request.complete(false, Component.translatable("mcdr-singleplayer.client.execution_failed", e.getClass().getSimpleName()).getString());
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
