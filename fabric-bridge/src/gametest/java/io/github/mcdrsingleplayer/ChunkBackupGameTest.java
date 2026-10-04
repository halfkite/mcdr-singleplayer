package io.github.mcdrsingleplayer;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.concurrent.TimeUnit;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;

/** Exercises official Chunk Backup, candy_tools, MCDR, file restore and the actual menu monitor. */
public final class ChunkBackupGameTest implements FabricClientGameTest {
    @Override public void runTest(ClientGameTestContext context) {
        String archive = System.getenv("MCDR_BRIDGE_TEST_CHUNK_BACKUP");
        if (archive == null) return;
        Path project = Path.of(System.getenv("MCDR_BRIDGE_TEST_ROOT"));
        Path game = FabricLoader.getInstance().getGameDir().toAbsolutePath();
        Path log = game.resolve("chunk-backup-game.log");
        var closeTasks = new java.util.concurrent.ConcurrentLinkedQueue<Runnable>();
        BridgeGameTest.mainBridge().setTestCloseDispatcher(closeTasks::add);
        var world = context.worldBuilder().create();
        Process process = null;
        try {
            Path save = world.getWorldSave().getSaveDirectory().toAbsolutePath();
            String player = context.computeOnClient(client -> client.player.getPlainTextName());
            var args = new ArrayList<String>(java.util.List.of(System.getenv("MCDR_BRIDGE_TEST_PYTHON"),
                project.resolve("scripts/chunk_backup_game_harness.py").toString(), "--game-dir", game.toString(),
                "--world-dir", save.toString(), "--player", player, "--chunk-backup", archive,
                "--candy-tools", System.getenv("MCDR_BRIDGE_TEST_CANDY_TOOLS")));
            process = new ProcessBuilder(args).redirectErrorStream(true).redirectOutput(log.toFile()).start();
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "Singleplayer world ready"), 1400);
            BridgeGameTest.check(PrimeBackupGameTest.contains(log, "Chunk Backup 2.0.3 singleplayer adapter ready"), "Adapter did not load");
            Path work = Path.of(Files.readString(game.resolve("chunk-backup-test-work.txt")));
            Path profile = work.resolve("plugindata").resolve(save.getFileName());
            world.getServer().runCommand("setblock 2 -60 2 minecraft:diamond_block");
            context.runOnClient(client -> client.player.connection.sendChat("!!chunk_test_probe " + player));
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "CB_ORIGINAL_GETTER_RESULT"), 800);
            context.runOnClient(client -> {
                client.getLanguageManager().setSelected("zh_cn");
                client.getLanguageManager().onResourceManagerReload(client.getResourceManager());
                client.player.connection.sendChat("!!chunk_test_probe " + player);
            });
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "CB_ORIGINAL_GETTER_RESULT None"), 800);
            world.getServer().runCommand("tp " + player + " 2 -59 2");
            context.runOnClient(client -> client.player.connection.sendChat("!!cb make 1 bridge-test"));
            context.waitFor(client -> Files.isRegularFile(profile.resolve("cb_files/dynamic_storage/slot1/info.json")), 2200);
            world.getServer().waitFor(server -> server.isAutoSave());
            context.runOnClient(client -> client.player.connection.sendChat("!!cb pmake 0 0 15 15 in 0 -s rectangle-test"));
            context.waitFor(client -> Files.isRegularFile(profile.resolve("cb_files/static_storage/slot1/info.json")), 1400);
            world.getServer().waitFor(server -> server.isAutoSave());
            context.runOnClient(client -> client.player.connection.sendChat("!!cb dmake 0 -s dimension-test"));
            context.waitFor(client -> Files.isRegularFile(profile.resolve("cb_files/static_storage/slot2/info.json")), 1400);
            world.getServer().waitFor(server -> server.isAutoSave());
            world.getServer().runCommand("setblock 2 -60 2 minecraft:gold_block");

            context.runOnClient(client -> client.player.connection.sendChat("!!cb back 1"));
            context.waitFor(client -> RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().running(), 600);
            // A running adapter status precedes CB's cancellable confirmation phase.
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "to confirm"), 600);
            context.runOnClient(client -> client.player.connection.sendChat("!!cb abort"));
            context.waitFor(client -> RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().status().equals("cancelled"), 600);
            BridgeGameTest.check(PrimeBackupGameTest.contains(log, "task aborted"), "CB did not acknowledge abort");
            BridgeGameTest.check(context.computeOnClient(client -> client.level != null), "Abort closed the world");

            context.runOnClient(client -> client.player.connection.sendChat("!!cb back 1 -c"));
            BridgeGameTest.awaitAsyncClose(context, closeTasks,
                client -> client.level == null && PrimeBackupGameTest.contains(log, "CB_TEST_RESTORE_GATE"), 2000);
            context.waitFor(client -> RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().stage().equals("restoring"), 600);
            BridgeGameTest.check(RestoreProgressMonitor.blocks(save.getFileName().toString()), "Restore did not lock the world entry");
            PrimeBackupGameTest.console(process, "!!spbridge internal retire");
            context.waitFor(client -> PrimeBackupGameTest.contains(log, "Server process stopped with code 0"), 600);
            BridgeGameTest.check(process.isAlive(), "Profile exited before Chunk Backup task finished");
            context.takeScreenshot("chunk-backup-waiting-for-restore");
            Files.writeString(profile.resolve("release-restore-gate"), "continue");
            context.waitFor(client -> RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().status().equals("completed"), 1800);
            Process first = process;
            context.waitFor(client -> !first.isAlive(), 800);
            BridgeGameTest.check(process.exitValue() == 0, "MCDR retirement failed");
            BridgeGameTest.check(!RestoreProgressMonitor.blocks(save.getFileName().toString()), "Successful restore did not unlock world");
            context.takeScreenshot("chunk-backup-restore-completed");
            var restored = world.getWorldSave().open();
            BridgeGameTest.check(restored.getServer().computeOnServer(server -> server.overworld().getBlockState(new BlockPos(2, -60, 2)).is(Blocks.DIAMOND_BLOCK)), "CB did not restore diamond block");

            // Restart the same MCDR profile and undo the restore from its overwrite slot.
            args.addAll(java.util.List.of("--reuse-work", work.toString()));
            Path undoLog = game.resolve("chunk-backup-undo.log");
            process = new ProcessBuilder(args).redirectErrorStream(true).redirectOutput(undoLog.toFile()).start();
            context.waitFor(client -> PrimeBackupGameTest.contains(undoLog, "Singleplayer world ready"), 1400);
            context.runOnClient(client -> client.player.connection.sendChat("!!cb restore -c"));
            BridgeGameTest.awaitAsyncClose(context, closeTasks,
                client -> client.level == null && RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().status().equals("completed"), 2000);
            var undone = world.getWorldSave().open();
            BridgeGameTest.check(undone.getServer().computeOnServer(server -> server.overworld().getBlockState(new BlockPos(2, -60, 2)).is(Blocks.GOLD_BLOCK)), "CB undo did not restore pre-restore gold block");
            undone.close();
            PrimeBackupGameTest.console(process, "!!MCDR server exit");
            Process second = process;
            context.waitFor(client -> !second.isAlive(), 800);
            BridgeGameTest.check(process.exitValue() == 0, "MCDR undo exit failed");
        } catch (IOException e) { throw new AssertionError(e); }
        finally {
            context.runOnClient(client -> {
                client.getLanguageManager().setSelected("en_us");
                client.getLanguageManager().onResourceManagerReload(client.getResourceManager());
            });
            BridgeGameTest.mainBridge().setTestCloseDispatcher(null);
            if (process != null && process.isAlive()) {
                process.descendants().forEach(ProcessHandle::destroyForcibly);
                process.destroy();
                try { if (!process.waitFor(5, TimeUnit.SECONDS)) process.destroyForcibly(); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            }
            if (context.computeOnClient(client -> client.level != null)) world.close();
        }
    }
}
