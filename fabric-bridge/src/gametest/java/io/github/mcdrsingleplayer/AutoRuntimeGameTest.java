package io.github.mcdrsingleplayer;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommands;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;

/** Real automatic startup, slash completion, recommendation, PB restore, profile reopen/switch. */
public final class AutoRuntimeGameTest implements FabricClientGameTest {
    @Override public void runTest(ClientGameTestContext context) {
        String commonPath = System.getenv("MCDR_BRIDGE_TEST_AUTO_COMMON");
        if (commonPath == null) return;
        Path game = FabricLoader.getInstance().getGameDir().toAbsolutePath();
        Path common = game.resolve("mcdr-singleplayer");
        BridgeGameTest.check(Files.isRegularFile(common.resolve("mcdr-singleplayer-config.yml")), "Mod config is outside shared root");
        BridgeGameTest.check(Files.isDirectory(common.resolve("runtime")) && Files.isDirectory(common.resolve("log")), "Runtime and log folders are missing");
        BridgeGameTest.check(!Files.exists(game.resolve("config/mcdr_singleplayer_bridge.json")), "Legacy mod config was recreated");
        BridgeGameTest.check(!Files.exists(common.resolve("worlds")), "Profile layout still has a worlds intermediate folder");
        String python = System.getenv("MCDR_BRIDGE_TEST_PYTHON");
        var messages = new CopyOnWriteArrayList<String>();
        var clicks = new CopyOnWriteArrayList<String>();
        var closeTasks = new java.util.concurrent.ConcurrentLinkedQueue<Runnable>();
        ClientReceiveMessageEvents.GAME.register((message, overlay) -> {
            messages.add(message.getString());
            message.visit((style, text) -> {
                if (style.getClickEvent() instanceof net.minecraft.network.chat.ClickEvent.RunCommand click) clicks.add(click.command());
                return java.util.Optional.empty();
            }, net.minecraft.network.chat.Style.EMPTY);
        });
        var bridge = BridgeGameTest.mainBridge();
        bridge.setTestCloseDispatcher(closeTasks::add);
        Path controllerLog = common.resolve("log/controller.log");
        int controllersBefore = PrimeBackupGameTest.count(controllerLog, "Controller ready;");
        int profilesBefore = PrimeBackupGameTest.count(controllerLog, "MCDR profile started:");
        try {
            Files.createDirectories(common.resolve("plugins"));
            if (System.getenv("MCDR_BRIDGE_TEST_PREINSTALLED") != null) {
                // Fabric rebuilds this test's game directory on every invocation.
                // Seed upstream files inside the fixture to exercise an existing installation.
                Path reference = Path.of(System.getenv("MCDR_BRIDGE_TEST_ROOT")).resolve(".reference");
                for (String name : new String[]{"PrimeBackup-v1.13.1.pyz", "Chunk_BackUp-v2.0.3.mcdr", "Candy_Tools-v1.0.2.mcdr"})
                    Files.copy(reference.resolve(name), common.resolve("plugins").resolve(name));
            }
            Files.writeString(common.resolve("plugins/test_command_probe.py"), """
                from mcdreforged.api.command import Literal, QuotableText
                import os, time
                from pathlib import Path
                PLUGIN_METADATA = {'id': 'test_command_probe', 'version': '1.0.0', 'dependencies': {'prime_backup': '==1.13.1', 'singleplayer_prime_backup': '==0.4.0'}}
                _export = None
                ExportBackupToDirectoryAction = None
                def on_load(server, previous):
                    global _export, ExportBackupToDirectoryAction
                    from prime_backup.action.export_backup_action_directory import ExportBackupToDirectoryAction
                    _export = ExportBackupToDirectoryAction._export_backup
                    def held_export(self, session, backup):
                        gate = Path(os.environ['MCDR_BRIDGE_COMMON']) / 'runtime/test-hold-restore'
                        deadline = time.monotonic() + 30
                        while gate.exists() and time.monotonic() < deadline:
                            time.sleep(0.05)
                        return _export(self, session, backup)
                    ExportBackupToDirectoryAction._export_backup = held_export
                    server.register_command(Literal(('!!extra', '!!extra_alias')).then(Literal('idle').runs(lambda source: source.reply('PB_BUSY' if server.get_plugin_instance('singleplayer_bridge').plugin.prime_busy() else 'PB_IDLE'))).then(Literal('nested').then(Literal('leaf').then(QuotableText('value').suggests(lambda: ['alpha', 'beta']).runs(lambda source, context: source.reply('EXTRA_OK '+context['value']))))))
                def on_unload(server):
                    ExportBackupToDirectoryAction._export_backup = _export
                """);
        } catch (IOException e) { throw new AssertionError(e); }
        bridge.enableTestAutomation(common, python);
        // No profile process is created merely by reaching the title screen.
        context.waitFor(client -> Files.exists(common.resolve("runtime/runtime-install.json")), 18000);
        context.waitFor(client -> PrimeBackupGameTest.count(controllerLog, "Controller ready;") > controllersBefore, 18000);
        BridgeGameTest.check(PrimeBackupGameTest.count(controllerLog, "MCDR profile started:") == profilesBefore, "A world profile started at the menu");
        String oldLanguage = context.computeOnClient(client -> client.getLanguageManager().getSelected());
        var languageReload = context.computeOnClient(client -> {
            client.getLanguageManager().setSelected("zh_cn");
            return client.reloadResourcePacks();
        });
        context.waitFor(client -> languageReload.isDone(), 2400);
        var world = context.worldBuilder().create();
        try {
            Path save = world.getWorldSave().getSaveDirectory().toAbsolutePath();
            Path profile = common.resolve("date").resolve(save.getFileName());
            Path log = common.resolve("log").resolve(profile.getFileName()).resolve("controller-child.log");
            // A new world has its own log; the controller can be ready before create() returns.
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "Singleplayer world ready"), 2400);
            context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!spbridge") != null, 1800);
            if (!Files.exists(common.resolve("plugins/PrimeBackup-v1.13.1.pyz"))) {
                context.waitFor(client -> clicks.contains("/!!spbridge install prime_backup") && clicks.contains("/!!spbridge install chunk_backup"), 1800);
                BridgeGameTest.check(messages.stream().filter(s -> s.contains("注意！！！ 本模组处于初步测试阶段")).count() == 3, "First-run warning was not repeated three times");
                BridgeGameTest.check(!clicks.contains("/!!spbridge config backup on"), "PB controls shown before installation");
                context.takeScreenshot("onboarding-first-install");
                context.runOnClient(client -> client.player.connection.sendCommand("!!spbridge install prime_backup"));
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("prime_backup 已安装并加载")), 6000);
                // MCDR unloads this test-only probe when PB is absent at startup.
                context.runOnClient(client -> client.player.connection.sendCommand("!!MCDR plugin load test_command_probe.py"));
            }
            context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!extra") != null, 1800);
            BridgeGameTest.check(Files.readString(common.resolve("permission.yml")).contains("- " + context.computeOnClient(client -> client.player.getPlainTextName())), "Main player not automatically granted owner");
            BridgeGameTest.check(Files.readString(common.resolve("config.yml")).contains("language: zh_cn"), "MCDR language did not follow client");
            var initial = config(profile);
            BridgeGameTest.check(initial.get("enabled").getAsBoolean() && !initial.getAsJsonObject("scheduled_backup").get("enabled").getAsBoolean() && !initial.getAsJsonObject("prune").get("enabled").getAsBoolean(), "Default PB consent incorrect");
            context.waitFor(client -> clicks.contains("/!!spbridge config backup on") && clicks.contains("/!!spbridge config auto_backup on") && clicks.contains("/!!spbridge config auto_delete on"), 1800);
            if (System.getenv("MCDR_BRIDGE_TEST_PREINSTALLED") != null) {
                BridgeGameTest.check(!clicks.contains("/!!spbridge install prime_backup") && !clicks.contains("/!!spbridge install chunk_backup"), "Existing plugins still showed installation buttons");
                BridgeGameTest.check(messages.stream().filter(s -> s.contains("注意！！！ 本模组处于初步测试阶段")).count() == 3, "Existing installation lost first-run warnings");
            }
            context.takeScreenshot("recommendation-click-options");
            if (!Files.exists(common.resolve("plugins/Chunk_BackUp-v2.0.3.mcdr"))) {
                context.runOnClient(client -> client.player.connection.sendCommand("!!spbridge install chunk_backup"));
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("chunk_backup 已安装并加载")), 6000);
                context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!cb") != null, 1800);
                BridgeGameTest.check(Files.exists(profile.resolve("cb_files/.singleplayer-world.json")), "CB install did not bind current save");
            }
            context.runOnClient(client -> client.player.connection.sendCommand("!!spbridge onboarding dismiss"));
            context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("已忽略，以后不再主动提示")), 1800);
            context.runOnClient(client -> client.player.connection.sendUnattendedCommand("!!spbridge config backup off", null));
            context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("备份已关闭")), 1800);
            BridgeGameTest.check(!config(profile).get("enabled").getAsBoolean(), "Backup disable choice not saved");
            context.runOnClient(client -> client.player.connection.sendUnattendedCommand("!!spbridge config backup on", null));
            context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("备份已开启")), 1800);
            BridgeGameTest.check(config(profile).get("enabled").getAsBoolean(), "Backup enable choice not saved");
            context.runOnClient(client -> client.player.connection.sendUnattendedCommand("!!spbridge config auto_backup on", null));
            context.waitFor(client -> config(profile).getAsJsonObject("scheduled_backup").get("enabled").getAsBoolean(), 1800);
            context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("自动备份已开启")), 1800);
            context.runOnClient(client -> client.player.connection.sendUnattendedCommand("!!spbridge config auto_delete on", null));
            context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("自动删除已开启")), 1800);
            BridgeGameTest.check(config(profile).getAsJsonObject("scheduled_backup").get("interval").getAsString().equals("4h"), "Wrong backup interval");
            var retention = config(profile).getAsJsonObject("prune").getAsJsonObject("regular_backup");
            BridgeGameTest.check(retention.get("last").getAsInt() == 40 && retention.get("day").getAsInt() == 30 && retention.get("week").getAsInt() == 30, "Wrong retention policy");
            var registered = context.computeOnClient(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!extra").getChild("nested").getChild("leaf").getChild("value") != null);
            BridgeGameTest.check(registered, "Plugin subcommands/arguments were not registered");
            context.runOnClient(client -> client.player.connection.sendCommand("!!extra_alias nested leaf alpha"));
            context.waitFor(client -> messages.contains("EXTRA_OK alpha"), 800);
            CompletableFuture<com.mojang.brigadier.suggestion.Suggestions> completions = context.computeOnClient(client -> {
                var dispatcher = ClientCommands.getActiveDispatcher();
                var source = (FabricClientCommandSource) client.getConnection().getSuggestionsProvider();
                return dispatcher.getCompletionSuggestions(dispatcher.parse("!!MCDR plugin reload singleplayer_b", source));
            });
            context.waitFor(client -> completions.isDone(), 800);
            BridgeGameTest.check(completions.join().getList().stream().anyMatch(s -> s.getText().contains("singleplayer_bridge")), "Native MCDR slash completion missing: " + completions.join().getList());
            context.runOnClient(client -> client.player.connection.sendCommand("!!MCDR plugin unload test_command_probe"));
            context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!extra") == null, 1200);
            context.runOnClient(client -> client.player.connection.sendCommand("!!MCDR plugin load test_command_probe.py"));
            context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!extra") != null, 1200);
            Path probe = common.resolve("plugins/test_command_probe.py");
            Files.writeString(probe, Files.readString(probe).replace("Literal('leaf')", "Literal('changed')"));
            context.runOnClient(client -> client.player.connection.sendCommand("!!MCDR plugin reload test_command_probe"));
            context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!extra").getChild("nested").getChild("changed") != null, 1200);
            BridgeGameTest.check(context.computeOnClient(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!extra").getChild("nested").getChild("leaf") == null), "Reload retained old plugin subcommands");
            world.getServer().runCommand("setblock 2 -60 2 minecraft:diamond_block");
            Files.writeString(save.resolve("auto-test-marker.txt"), "before");
            context.runOnClient(client -> client.player.connection.sendCommand("!!pb make automatic-test"));
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "Create backup #1 done"), 2400);
            context.waitFor(client -> {
                if (messages.contains("PB_IDLE")) return true;
                client.player.connection.sendCommand("!!extra idle");
                return false;
            }, 800);
            world.getServer().runCommand("setblock 2 -60 2 minecraft:gold_block");
            Files.writeString(save.resolve("auto-test-marker.txt"), "after");
            Path restoreGate = common.resolve("runtime/test-hold-restore");
            Files.writeString(restoreGate, "Hold only this isolated test's restore for UI and entry-lock checks");
            context.runOnClient(client -> client.player.connection.sendCommand("!!pb back 1 --confirm"));
            BridgeGameTest.awaitAsyncClose(context, closeTasks, client -> client.level == null && RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().stage().equals("restoring"), 2400);
            BridgeGameTest.check(context.computeOnClient(client -> client.gui.screen() instanceof net.minecraft.client.gui.screens.TitleScreen), "Restore progress did not remain on the title screen");
            context.takeScreenshot("automatic-restore-running");
            BridgeGameTest.check(context.computeOnClient(client -> net.fabricmc.fabric.api.client.screen.v1.Screens.getWidgets(client.gui.screen()).stream().filter(widget -> widget.visible).allMatch(widget -> !widget.active && widget.getMessage().getString().equals("正在回档…"))), "Menu still exposes an active entry during restore");
            context.runOnClient(client -> client.createWorldOpenFlows().openWorld(save.getFileName().toString(), () -> {}));
            BridgeGameTest.check(context.computeOnClient(client -> client.level == null && client.gui.screen() instanceof net.minecraft.client.gui.screens.TitleScreen), "Restoring world was allowed to open");
            BridgeGameTest.check("after".equals(Files.readString(save.resolve("auto-test-marker.txt"))), "Test did not hold before restoring files");
            Files.deleteIfExists(restoreGate);
            context.waitFor(client -> RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().status().equals("completed"), 2400);
            context.takeScreenshot("automatic-restore-completed");
            BridgeGameTest.check(!RestoreProgressMonitor.blocks(save.getFileName().toString()), "Completed restore did not unlock world");
            context.runOnClient(client -> {
                var button = net.fabricmc.fabric.api.client.screen.v1.Screens.getWidgets(client.gui.screen()).stream()
                    .filter(widget -> widget.visible && widget.active && widget.getMessage().getString().equals("返回主菜单"))
                    .findFirst().orElseThrow(() -> new AssertionError("No restore acknowledgment button"));
                ((net.minecraft.client.gui.components.Button) button).onPress(null);
            });
            context.waitFor(client -> RestoreProgressMonitor.instance.visible() == null && net.fabricmc.fabric.api.client.screen.v1.Screens.getWidgets(client.gui.screen()).stream().anyMatch(widget -> widget.visible && widget.active), 100);
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "bye"), 1200);
            BridgeGameTest.check("before".equals(Files.readString(save.resolve("auto-test-marker.txt"))), "Automatic profile restore failed");
            int warningsBeforeReentry = (int) messages.stream().filter(s -> s.contains("注意！！！ 本模组处于初步测试阶段")).count();
            var reopened = world.getWorldSave().open();
            try {
                context.waitFor(client -> PrimeBackupGameTest.count(log, "Singleplayer world ready") >= 2, 2400);
                BridgeGameTest.check(reopened.getServer().computeOnServer(server -> server.overworld().getBlockState(new BlockPos(2, -60, 2)).is(Blocks.DIAMOND_BLOCK)), "Automatic reopen did not restore blocks");
                context.waitTicks(30);
                BridgeGameTest.check(messages.stream().filter(s -> s.contains("注意！！！ 本模组处于初步测试阶段")).count() == warningsBeforeReentry, "Dismissed onboarding repeated on reentry");
                context.takeScreenshot("automatic-profile-restored");
            } finally { reopened.close(); }
            context.waitFor(client -> PrimeBackupGameTest.count(log, "bye") >= 2, 1200);
            try (var second = context.worldBuilder().create()) {
                Path secondSave = second.getWorldSave().getSaveDirectory().toAbsolutePath();
                Path secondProfile = common.resolve("date").resolve(secondSave.getFileName());
                Path secondLog = common.resolve("log").resolve(secondProfile.getFileName()).resolve("controller-child.log");
                context.waitFor(client -> PrimeBackupGameTest.contains(secondLog, "Singleplayer world ready"), 2400);
                context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!spbridge") != null, 1200);
                var config = com.google.gson.JsonParser.parseString(Files.readString(secondProfile.resolve("config/prime_backup/config.json"))).getAsJsonObject();
                BridgeGameTest.check(config.get("enabled").getAsBoolean() && !config.getAsJsonObject("scheduled_backup").get("enabled").getAsBoolean() && !config.getAsJsonObject("prune").get("enabled").getAsBoolean(), "Second world inherited first-world choices");
                BridgeGameTest.check(emptyBackups(common, secondProfile), "Second world inherited backup database");
                context.runOnClient(client -> client.player.connection.sendCommand("!!spbridge profile import \"" + save.getFileName() + "\" --replace"));
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("已导入")), 800);
                var imported = com.google.gson.JsonParser.parseString(Files.readString(secondProfile.resolve("config/prime_backup/config.json"))).getAsJsonObject();
                BridgeGameTest.check(imported.getAsJsonObject("backup").getAsJsonArray("targets").get(0).getAsString().equals(secondSave.getFileName().toString()), "Imported profile retained old-world target");
                BridgeGameTest.check(emptyBackups(common, secondProfile), "Import copied backup data");
            }
            context.takeScreenshot("automatic-profile-world-switch");
        } catch (IOException e) { throw new AssertionError(e); }
        finally {
            bridge.setTestCloseDispatcher(null);
            var resetLanguage = context.computeOnClient(client -> {
                client.getLanguageManager().setSelected(oldLanguage);
                return client.reloadResourcePacks();
            });
            context.waitFor(client -> resetLanguage.isDone(), 2400);
            if (context.computeOnClient(client -> client.level != null)) world.close();
        }
    }

    private static com.google.gson.JsonObject config(Path profile) {
        try { return com.google.gson.JsonParser.parseString(Files.readString(profile.resolve("config/prime_backup/config.json"))).getAsJsonObject(); }
        catch (IOException e) { throw new AssertionError(e); }
    }

    private static boolean emptyBackups(Path common, Path profile) throws IOException {
        Path database = profile.resolve("pb_files/prime_backup.db");
        BridgeGameTest.check(Files.isRegularFile(database), "PB database did not use its native pb_files directory");
        var process = new ProcessBuilder(common.resolve("runtime/.bridge-venv/Scripts/python.exe").toString(), "-c",
            "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select count(*) from backup').fetchone()[0])", database.toString()).start();
        try {
            if (!process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)) throw new IOException("Database check timed out");
            return process.exitValue() == 0 && new String(process.getInputStream().readAllBytes()).strip().equals("0");
        } catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new IOException(e); }
    }
}
