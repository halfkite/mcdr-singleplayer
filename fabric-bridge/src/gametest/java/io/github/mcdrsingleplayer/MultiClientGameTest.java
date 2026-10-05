package io.github.mcdrsingleplayer;

import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.multiplayer.resolver.ServerAddress;
import net.minecraft.server.MinecraftServer;

/** Two real Minecraft JVMs share one game directory and connect through vanilla LAN. */
public final class MultiClientGameTest implements FabricClientGameTest {
    static boolean selected() { return "1".equals(System.getenv("MCDR_BRIDGE_TEST_MULTI_CLIENT")); }
    private static boolean guest() { return "guest".equals(System.getenv("MCDR_BRIDGE_TEST_MULTI_ROLE")); }

    @Override public void runTest(ClientGameTestContext context) {
        if (!selected()) return;
        Path game = FabricLoader.getInstance().getGameDir().toAbsolutePath();
        Path common = game.resolve("mcdr-singleplayer");
        Path exchange = common.resolve("runtime/lan-test");
        var messages = new CopyOnWriteArrayList<String>();
        ClientReceiveMessageEvents.GAME.register((message, overlay) -> messages.add(message.getString()));
        context.runOnClient(client -> client.options.pauseOnLostFocus = false);
        try {
            Files.createDirectories(exchange);
            PrimeBackupGameTest.checkConfluxNativeCache(game, null);
            if (FabricLoader.getInstance().isModLoaded("confluxmap")) {
                Files.writeString(exchange.resolve(guest() ? "guest-native-cache" : "host-native-cache"),
                        ConfluxNativeCache.directory(game).toString());
            }
            if (guest()) runGuest(context, common, exchange, messages);
            else runHost(context, common, exchange, messages);
        } catch (IOException e) { throw new AssertionError(e); }
    }

    private static void runHost(ClientGameTestContext context, Path common, Path exchange,
            List<String> messages) throws IOException {
        Files.createDirectories(common.resolve("plugins"));
        Files.writeString(common.resolve("plugins/lan_probe.py"), """
            from mcdreforged.api.command import Literal, QuotableText
            PLUGIN_METADATA = {'id': 'lan_probe', 'version': '1.0.0'}
            def on_load(server, previous):
                server.register_command(Literal(('!!lanprobe', '!!lanalias')).then(Literal('echo').then(QuotableText('value').suggests(lambda: ['alpha', 'beta']).runs(lambda source, context: source.reply('LAN_REPLY '+source.player+' '+context['value'])))).then(Literal('owner').requires(lambda source: source.has_permission(4)).runs(lambda source: source.reply('LAN_OWNER '+source.player))))
            """);
        BridgeGameTest.mainBridge().enableTestAutomation(common, System.getenv("MCDR_BRIDGE_TEST_PYTHON"));
        context.waitFor(client -> PrimeBackupGameTest.contains(common.resolve("log/controller.log"), "Controller ready;"), 18000);
        try (var world = context.worldBuilder().create()) {
            Path save = world.getWorldSave().getSaveDirectory();
            Path log = common.resolve("log").resolve(save.getFileName()).resolve("controller-child.log");
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "Singleplayer world ready"), 2400);
            context.waitFor(client -> client.getConnection().getCommands().getRoot().getChild("!!lanprobe") != null, 2400);
            String owner = context.computeOnClient(client -> client.player.getPlainTextName());
            send(context, "!!lanprobe echo before");
            context.waitFor(client -> messages.contains("LAN_REPLY " + owner + " before"), 1200);
            int port;
            try (var socket = new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) { port = socket.getLocalPort(); }
            int lanPort = port;
            BridgeGameTest.check(world.getServer().computeOnServer(server -> {
                server.setUsesAuthentication(false); // Fabric's test accounts have no Mojang session.
                return server.publishServer(MinecraftServer.MultiplayerScope.LAN, false, lanPort);
            }), "Could not publish LAN test world");
            Files.writeString(exchange.resolve("address"), "127.0.0.1:" + port);
            Process second = launchGuest(exchange);
            try {
                context.waitFor(client -> Files.exists(exchange.resolve("guest-connected")) || !second.isAlive(), 18000);
                BridgeGameTest.check(second.isAlive(), "Guest exited before connecting; see guest-process.log");
                send(context, "!!lanalias echo with-guest");
                context.waitFor(client -> messages.contains("LAN_REPLY " + owner + " with-guest"), 1200);
                send(context, "!!lanprobe owner");
                context.waitFor(client -> messages.contains("LAN_OWNER " + owner), 1200);
                context.waitFor(client -> Files.exists(exchange.resolve("guest-commands-passed")) || !second.isAlive(), 18000);
                BridgeGameTest.check(Files.exists(exchange.resolve("guest-commands-passed")), "Guest command test failed; see guest-process.log");
                BridgeGameTest.check(!messages.contains("LAN_REPLY LanGuest alpha"), "Guest reply was sent to the host");
                String permissions = Files.readString(common.resolve("permission.yml"));
                String owners = permissions.substring(permissions.indexOf("\nowner:"), permissions.indexOf("\nadmin:"));
                BridgeGameTest.check(!owners.contains("LanGuest"), "Guest inherited host permission");
                // Refresh the graph while the guest is connected; both clients must receive it.
                Path plugin = common.resolve("plugins/lan_probe.py");
                Files.writeString(plugin, Files.readString(plugin).replace("Literal('echo')", "Literal('updated')"));
                send(context, "!!MCDR plugin reload lan_probe");
                context.waitFor(client -> client.getConnection().getCommands().getRoot().getChild("!!lanprobe").getChild("updated") != null, 2400);
                Files.writeString(exchange.resolve("reloaded"), "ready");
                context.waitFor(client -> Files.exists(exchange.resolve("guest-passed")) || !second.isAlive(), 18000);
                BridgeGameTest.check(Files.exists(exchange.resolve("guest-passed")), "Guest reload test failed; see guest-process.log");
                if (FabricLoader.getInstance().isModLoaded("confluxmap")) {
                    BridgeGameTest.check(!Files.readString(exchange.resolve("host-native-cache")).equals(Files.readString(exchange.resolve("guest-native-cache"))), "Two clients shared the same native extraction directory");
                    PrimeBackupGameTest.checkConfluxNativeCache(FabricLoader.getInstance().getGameDir(), world.getWorldSave().getSaveDirectory());
                }
                context.waitFor(client -> !second.isAlive(), 6000);
                BridgeGameTest.check(second.exitValue() == 0, "Guest Minecraft did not exit successfully");
                send(context, "!!lanprobe updated after-guest");
                context.waitFor(client -> messages.contains("LAN_REPLY " + owner + " after-guest"), 1200);
                BridgeGameTest.check(PrimeBackupGameTest.count(common.resolve("log/controller.log"), "MCDR profile started:") == 1,
                        "Second client replaced or restarted the host controller");
                context.takeScreenshot("lan-host-after-second-client");
            } finally {
                if (second.isAlive()) second.destroyForcibly();
            }
        }
    }

    private static void runGuest(ClientGameTestContext context, Path common, Path exchange,
            List<String> messages) throws IOException {
        BridgeGameTest.check(context.computeOnClient(client -> client.getUser().getName().equals("LanGuest")), "Guest did not get a different account name");
        BridgeGameTest.mainBridge().enableTestAutomation(common, System.getenv("MCDR_BRIDGE_TEST_PYTHON"));
        String address = Files.readString(exchange.resolve("address")).strip();
        context.runOnClient(client -> ConnectScreen.startConnecting(new TitleScreen(), client,
                ServerAddress.parseString(address), new ServerData("LAN regression", address, ServerData.Type.LAN), false, null));
        try {
            context.waitFor(client -> client.player != null && client.level != null, 6000);
            context.waitFor(client -> client.getConnection().getCommands().getRoot().getChild("!!lanprobe") != null, 2400);
            BridgeGameTest.check(context.computeOnClient(client -> client.getSingleplayerServer() == null), "Guest started its own world");
            Files.writeString(exchange.resolve("guest-connected"), "ready");
            send(context, "!!lanalias echo alpha");
            context.waitFor(client -> messages.contains("LAN_REPLY LanGuest alpha"), 2400);
            var suggestions = context.computeOnClient(client -> {
                var dispatcher = client.getConnection().getCommands();
                var input = new com.mojang.brigadier.StringReader("/!!lanprobe echo a");
                input.skip();
                return dispatcher.getCompletionSuggestions(dispatcher.parse(input, client.getConnection().getSuggestionsProvider()));
            });
            context.waitFor(client -> suggestions.isDone(), 2400);
            BridgeGameTest.check(suggestions.join().getList().stream().anyMatch(item -> item.apply("/!!lanprobe echo a").equals("/!!lanprobe echo alpha")), "LAN slash/argument completion failed: " + suggestions.join());
            send(context, "!!lanprobe owner");
            context.waitFor(client -> messages.stream().anyMatch(item -> item.contains("Requirement not met")), 1200);
            BridgeGameTest.check(messages.stream().noneMatch(item -> item.startsWith("LAN_OWNER")), "Guest ran owner-only command");
            Files.writeString(exchange.resolve("guest-commands-passed"), "ready");
            context.waitFor(client -> Files.exists(exchange.resolve("reloaded")), 6000);
            context.waitFor(client -> client.getConnection().getCommands().getRoot().getChild("!!lanprobe").getChild("updated") != null, 2400);
            BridgeGameTest.check(context.computeOnClient(client -> client.getConnection().getCommands().getRoot().getChild("!!lanprobe").getChild("echo") == null), "LAN reload retained old subcommand");
            send(context, "!!lanprobe updated beta");
            context.waitFor(client -> messages.contains("LAN_REPLY LanGuest beta"), 2400);
            context.takeScreenshot("lan-guest-command-reply");
            Files.writeString(exchange.resolve("guest-passed"), "ready");
        } finally {
            context.runOnClient(client -> client.disconnect(new TitleScreen(), false));
            context.waitFor(client -> client.level == null && client.player == null, 100);
            context.waitTicks(2);
            context.setScreen(TitleScreen::new);
        }
    }

    private static void send(ClientGameTestContext context, String command) {
        context.runOnClient(client -> client.player.connection.sendCommand(command));
    }

    private static Process launchGuest(Path exchange) throws IOException {
        // ProcessHandle arguments are unavailable on Windows. Reuse the test JVM's
        // runtime/classpath and Fabric's parsed game arguments instead of shell quoting.
        var command = new ArrayList<>(List.of(Path.of(System.getProperty("java.home"), "bin",
                System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java").toString()));
        command.addAll(java.lang.management.ManagementFactory.getRuntimeMXBean().getInputArguments());
        System.getProperties().stringPropertyNames().stream()
                .filter(key -> key.startsWith("fabric.") || key.startsWith("log4j.") || key.startsWith("log4j2."))
                .forEach(key -> command.add("-D" + key + "=" + System.getProperty(key)));
        command.addAll(List.of("-cp", System.getProperty("java.class.path"), "net.fabricmc.loader.impl.launch.knot.KnotClient"));
        String[] arguments = FabricLoader.getInstance().getLaunchArguments(false);
        for (int i = 0; i < arguments.length; i++) {
            if (arguments[i].equals("--username") || arguments[i].equals("--uuid")) { i++; continue; }
            command.add(arguments[i]);
        }
        command.addAll(List.of("--username", "LanGuest", "--uuid", "ed2135be-c94b-467b-a908-b5d62f71c994"));
        var builder = new ProcessBuilder(command).directory(Path.of(System.getProperty("user.dir")).toFile())
                .redirectErrorStream(true).redirectOutput(exchange.resolve("guest-process.log").toFile());
        builder.environment().put("MCDR_BRIDGE_TEST_MULTI_ROLE", "guest");
        return builder.start();
    }
}
