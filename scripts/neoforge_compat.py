"""NeoForge event bindings; the protocol, save checks and restore locks stay shared."""
from pathlib import Path


def adapt(text, name, row):
    text = '\n'.join(line for line in text.splitlines() if not line.startswith('import net.fabricmc.')) + '\n'
    if name == 'SingleplayerBridge.java':
        text = text.replace('public final class SingleplayerBridge implements ModInitializer', 'public final class SingleplayerBridge')
        text = text.replace('    @Override\n    public void onInitialize()', '    public void onInitialize()')
        text = text.replace('import org.slf4j.Logger;', '''import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import org.slf4j.Logger;''')
        pairs = {
            'FabricLoader': 'NeoPlatform.Loader',
            'ClientLifecycleEvents.CLIENT_STARTED.register': 'NeoPlatform.started',
            'ClientLifecycleEvents.CLIENT_STOPPING.register': 'NeoPlatform.stopping',
            'ServerLifecycleEvents.SERVER_STARTED.register': 'NeoPlatform.serverStarted',
            'ServerLifecycleEvents.SERVER_STOPPED.register': 'NeoPlatform.serverStopped',
            'ClientTickEvents.END_CLIENT_TICK.register': 'NeoPlatform.tick',
            'ServerMessageEvents.CHAT_MESSAGE.register((message, player, chatType)': 'NeoPlatform.chat((message, player)',
            'message.signedContent()': 'message',
            'ServerMessageEvents.GAME_MESSAGE.register': 'NeoPlatform.gameMessage',
            'ServerPlayConnectionEvents.JOIN.register((listener, sender, server)': 'NeoPlatform.join((player, server)',
            'ServerPlayConnectionEvents.DISCONNECT.register((listener, server)': 'NeoPlatform.leave((player, server)',
            'listener.player': 'player',
            'ClientCommandRegistrationCallback.EVENT.register((dispatcher, context)': 'NeoPlatform.commands((dispatcher, context)',
            'FabricClientCommandSource': 'CommandSourceStack',
            'ClientCommands': 'Commands',
            'source -> source.getPlayer() != null': 'source -> Minecraft.getInstance().player != null',
            'source.getPlayer().getName().getString()': 'source.getTextName()',
            'source.sendError(': 'source.sendFailure(',
            'source.sendFeedback(Component.translatable("mcdr-singleplayer.client.setup_submitted"))':
                'source.sendSuccess(() -> Component.translatable("mcdr-singleplayer.client.setup_submitted"), false)',
        }
        for old, new in pairs.items():
            text = text.replace(old, new)
    elif name == 'ClientCommandTree.java':
        text = text.replace('import com.google.gson.JsonArray;', '''import net.minecraft.commands.Commands;
import net.minecraft.commands.CommandSourceStack;
import net.neoforged.neoforge.client.ClientCommandHandler;
import com.google.gson.JsonArray;''')
        text = text.replace('FabricClientCommandSource', 'CommandSourceStack').replace('ClientCommands', 'Commands')
        text = text.replace('        if (dispatcher == null) return;', '''        var active = ClientCommandHandler.getDispatcher();
        if (active != dispatcher && active != null) attach(active);
        if (dispatcher == null) return;''')
        text = text.replace('command.getSource().getPlayer().getName().getString()', 'net.minecraft.client.Minecraft.getInstance().player.getName().getString()')
        text = text.replace('Commands.refreshCommandCompletions();', 'refreshCompletions();')
        marker = '    @SuppressWarnings("unchecked")\n    private void removeOwned()'
        text = text.replace(marker, '''    @SuppressWarnings({"rawtypes", "unchecked"})
    private void refreshCompletions() {
        var connection = net.minecraft.client.Minecraft.getInstance().getConnection();
        if (connection == null) return;
        for (String name : owned) connection.getCommands().getRoot().addChild((CommandNode) dispatcher.getRoot().getChild(name));
    }

''' + marker)
        text = text.replace('owned.forEach(nodes::remove);', '''owned.forEach(nodes::remove);
                var connection = net.minecraft.client.Minecraft.getInstance().getConnection();
                if (connection != null) {
                    Map<String, ?> suggestions = (Map<String, ?>) field.get(connection.getCommands().getRoot());
                    owned.forEach(suggestions::remove);
                }''')
    elif name == 'RestoreTitleOverlay.java':
        text = text.replace('ScreenEvents.', 'NeoScreens.').replace('Screens.', 'NeoScreens.')
        # Replacing ScreenEvents first must not alter the new NeoScreens prefix twice.
        text = text.replace('NeoNeoScreens', 'NeoScreens')
    return text


def write_platform(source_root, row):
    game = row['minecraft']
    package = 'io.github.mcdrsingleplayer.v' + game.replace('.', '_')
    root = source_root / Path(package.replace('.', '/'))
    root.mkdir(parents=True, exist_ok=True)
    text = '''package PACKAGE;

import java.util.function.Consumer;
import java.util.function.BiConsumer;
import net.minecraft.client.Minecraft;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.CommandBuildContext;
import com.mojang.brigadier.CommandDispatcher;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.client.event.*;
import net.neoforged.neoforge.event.*;
import net.neoforged.neoforge.event.entity.player.PlayerEvent;
import net.neoforged.neoforge.event.server.*;

final class NeoPlatform {
    static final class Loader {
        static Loader getInstance() { return new Loader(); }
        java.nio.file.Path getGameDir() { return net.neoforged.fml.loading.FMLPaths.GAMEDIR.get(); }
        boolean isModLoaded(String id) { return net.neoforged.fml.ModList.get().isLoaded(id); }
    }
    static void started(Consumer<Minecraft> action) {
        NeoForge.EVENT_BUS.addListener(new Consumer<ClientTickEvent.Post>() {
            boolean fired;
            public void accept(ClientTickEvent.Post event) {
                if (!fired) { fired = true; action.accept(Minecraft.getInstance()); }
            }
        });
    }
    static void stopping(Consumer<Minecraft> action) {
        NeoForge.EVENT_BUS.addListener((GameShuttingDownEvent event) -> action.accept(Minecraft.getInstance()));
    }
    static void tick(Consumer<Minecraft> action) {
        NeoForge.EVENT_BUS.addListener((ClientTickEvent.Post event) -> action.accept(Minecraft.getInstance()));
    }
    static void serverStarted(Consumer<MinecraftServer> action) {
        NeoForge.EVENT_BUS.addListener((ServerStartedEvent event) -> action.accept(event.getServer()));
    }
    static void serverStopped(Consumer<MinecraftServer> action) {
        NeoForge.EVENT_BUS.addListener((ServerStoppedEvent event) -> action.accept(event.getServer()));
    }
    static void join(BiConsumer<ServerPlayer, MinecraftServer> action) {
        NeoForge.EVENT_BUS.addListener((PlayerEvent.PlayerLoggedInEvent event) -> {
            if (event.getEntity() instanceof ServerPlayer player) action.accept(player, player.level().getServer());
        });
    }
    static void leave(BiConsumer<ServerPlayer, MinecraftServer> action) {
        NeoForge.EVENT_BUS.addListener((PlayerEvent.PlayerLoggedOutEvent event) -> {
            if (event.getEntity() instanceof ServerPlayer player) action.accept(player, player.level().getServer());
        });
    }
    static void chat(BiConsumer<String, ServerPlayer> action) {
        NeoForge.EVENT_BUS.addListener((ServerChatEvent event) -> action.accept(event.getRawText(), event.getPlayer()));
    }
    interface GameMessage { void accept(MinecraftServer server, Component text, boolean overlay); }
    static void gameMessage(GameMessage action) {
        NeoForge.EVENT_BUS.addListener((ClientChatReceivedEvent.System event) -> {
            var server = Minecraft.getInstance().getSingleplayerServer();
            if (server != null) action.accept(server, event.getMessage(), event.isOverlay());
        });
    }
    static void commands(BiConsumer<CommandDispatcher<CommandSourceStack>, CommandBuildContext> action) {
        NeoForge.EVENT_BUS.addListener((RegisterClientCommandsEvent event) -> action.accept(event.getDispatcher(), event.getBuildContext()));
    }
}
'''.replace('PACKAGE', package)
    (root / 'NeoPlatform.java').write_text(text, encoding='utf8')
    extracted = tuple(map(int, game.split('.'))) >= (26, 1)
    graphics = 'GuiGraphicsExtractor' if extracted else 'GuiGraphics'
    text = '''package PACKAGE;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GRAPHICS;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.screens.Screen;
import net.neoforged.neoforge.client.event.ScreenEvent;
import net.neoforged.neoforge.common.NeoForge;

final class NeoScreens {
    interface Init { void accept(Minecraft client, Screen screen, int width, int height); }
    interface Draw { void accept(Screen screen, GRAPHICS graphics, int x, int y, float ticks); }
    static final class InitRegistry {
        void register(Init action) { init.add(action); }
    }
    static final class DrawRegistry {
        final List<Draw> actions = new ArrayList<>();
        void register(Draw action) { actions.add(action); }
    }
    static final List<Init> init = new ArrayList<>();
    static final InitRegistry AFTER_INIT = new InitRegistry();
    static Screen active;
    static ScreenEvent.Init.Post initializing;
    static DrawRegistry before = new DrawRegistry(), after = new DrawRegistry();
    static {
        NeoForge.EVENT_BUS.addListener((ScreenEvent.Init.Post event) -> {
            Screen parent = active;
            DrawRegistry parentBefore = before, parentAfter = after;
            ScreenEvent.Init.Post parentInit = initializing;
            active = event.getScreen();
            before = new DrawRegistry(); after = new DrawRegistry();
            initializing = event;
            try {
                for (Init action : init) action.accept(Minecraft.getInstance(), active, active.width, active.height);
            } finally {
                initializing = parentInit;
                if (parentInit != null) { active = parent; before = parentBefore; after = parentAfter; }
            }
        });
        NeoForge.EVENT_BUS.addListener((ScreenEvent.Render.Pre event) -> {
            if (event.getScreen() == active) for (Draw action : before.actions)
                action.accept(active, event.getGuiGraphics(), event.getMouseX(), event.getMouseY(), event.getPartialTick());
        });
        NeoForge.EVENT_BUS.addListener((ScreenEvent.Render.Post event) -> {
            if (event.getScreen() == active) for (Draw action : after.actions)
                action.accept(active, event.getGuiGraphics(), event.getMouseX(), event.getMouseY(), event.getPartialTick());
        });
    }
    static DrawRegistry beforeRender(Screen screen) { return before; }
    static DrawRegistry afterRender(Screen screen) { return after; }
    static DrawRegistry beforeExtract(Screen screen) { return before; }
    static DrawRegistry afterExtract(Screen screen) { return after; }
    static List<AbstractWidget> getWidgets(Screen screen) {
        return new java.util.AbstractList<>() {
            private List<AbstractWidget> values() { return screen.children().stream().filter(AbstractWidget.class::isInstance).map(AbstractWidget.class::cast).toList(); }
            public AbstractWidget get(int index) { return values().get(index); }
            public int size() { return values().size(); }
            public boolean add(AbstractWidget widget) {
                if (initializing == null || initializing.getScreen() != screen) throw new IllegalStateException("Widget added outside screen initialization");
                initializing.addListener(widget); return true;
            }
        };
    }
}
'''.replace('PACKAGE', package).replace('GRAPHICS', graphics)
    (root / 'NeoScreens.java').write_text(text, encoding='utf8')
