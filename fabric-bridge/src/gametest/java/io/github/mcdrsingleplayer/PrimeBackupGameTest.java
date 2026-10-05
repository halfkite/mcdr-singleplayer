package io.github.mcdrsingleplayer;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipFile;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.item.Items;

public final class PrimeBackupGameTest implements FabricClientGameTest {
    @Override public void runTest(ClientGameTestContext context) {
        if (MultiClientGameTest.selected()) return;
        String archive = System.getenv("MCDR_BRIDGE_TEST_PRIME_BACKUP");
        if (archive == null) return;
        String python = System.getenv("MCDR_BRIDGE_TEST_PYTHON");
        Path project = Path.of(System.getenv("MCDR_BRIDGE_TEST_ROOT"));
        boolean baseline = "1".equals(System.getenv("MCDR_BRIDGE_TEST_PB_BASELINE"));
        var messages = new CopyOnWriteArrayList<String>();
        var closeTasks = new java.util.concurrent.ConcurrentLinkedQueue<Runnable>();
        BridgeGameTest.mainBridge().setTestCloseDispatcher(closeTasks::add);
        ClientReceiveMessageEvents.GAME.register((message, overlay) -> messages.add(message.getString()));
        var world = context.worldBuilder().create();
        Process process = null;
        Process fileHolder = null;
        Path game = FabricLoader.getInstance().getGameDir().toAbsolutePath();
        Path log = game.resolve(baseline ? "prime-backup-baseline.log" : "prime-backup-adapted.log");
        try {
            Path save = world.getWorldSave().getSaveDirectory().toAbsolutePath();
            checkConfluxNativeCache(game, save);
            Path heldConfig = save.resolve("syncmatica/config.json");
            Files.createDirectories(heldConfig.getParent());
            if (!Files.exists(heldConfig)) Files.writeString(heldConfig, "{\"test\":true}");
            if (FabricLoader.getInstance().isModLoaded("syncmatica")) {
                world.getServer().runOnServer(server -> {
                    try {
                        Class<?> mod = Class.forName("ch.endte.syncmatica.Syncmatica");
                        Object syncContext = mod.getMethod("getContext", net.minecraft.resources.Identifier.class)
                                .invoke(null, mod.getField("SERVER_CONTEXT").get(null));
                        // The original 0.3.20 method leaks a reader each time existing
                        // configuration is loaded; keep the same game process alive.
                        for (int i = 0; i < 3; i++) syncContext.getClass().getMethod("loadConfiguration").invoke(syncContext);
                        Path moved = heldConfig.resolveSibling("config.json.handle-test");
                        Files.move(heldConfig, moved);
                        Files.move(moved, heldConfig);
                    } catch (Exception e) { throw new AssertionError("Syncmatica still holds its configuration reader", e); }
                });
            }
            String player = context.computeOnClient(client -> client.player.getPlainTextName());
            var args = new ArrayList<String>(java.util.List.of(python, project.resolve("scripts/prime_backup_game_harness.py").toString(),
                    "--game-dir", game.toString(), "--world-dir", save.toString(), "--player", player, "--prime-backup", archive));
            if (baseline) args.add("--baseline");
            process = new ProcessBuilder(args).redirectErrorStream(true).redirectOutput(log.toFile()).start();
            context.waitFor(client -> contains(log, "Singleplayer world ready"), 1200);
            if (!baseline) {
                world.getServer().runCommand("setblock 2 -60 2 minecraft:diamond_block");
                world.getServer().runCommand("item replace entity @a hotbar.0 with minecraft:diamond 7");
                Files.writeString(save.resolve("bridge-test-marker.txt"), "original-backup-content", StandardCharsets.UTF_8);
            }
            context.runOnClient(client -> client.player.connection.sendChat("!!pb make bridge-test"));
            if (baseline) {
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("Waiting for the world to save timed out")), 800);
                BridgeGameTest.check(contains(log, "Unknown or incomplete command"), "Expected missing integrated save commands");
                context.takeScreenshot("prime-backup-baseline-failure");
            } else {
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("Backup completed, ID")), 1800);
                world.getServer().waitFor(server -> server.isAutoSave());
                context.takeScreenshot("prime-backup-online-backup");
                // Stock commands and real export content, not only a successful log line.
                context.runOnClient(client -> client.player.connection.sendChat("!!pb list"));
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("bridge-test") && s.contains("#1")), 800);
                context.runOnClient(client -> client.player.connection.sendChat("!!pb show 1"));
                context.runOnClient(client -> client.player.connection.sendChat("!!pb export 1 zip"));
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("Exported backup")), 1600);
                Path work = Path.of(Files.readString(game.resolve("prime-backup-test-work.txt")));
                Path exported;
                try (var files = Files.list(work.resolve("plugindata").resolve(save.getFileName()).resolve("pb_files/export"))) {
                    exported = files.filter(p -> p.toString().endsWith(".zip")).findFirst().orElseThrow();
                }
                try (var zip = new ZipFile(exported.toFile())) {
                    var entry = zip.getEntry(save.getFileName() + "/bridge-test-marker.txt");
                    BridgeGameTest.check(entry != null, "Missing world marker in export");
                    BridgeGameTest.check("original-backup-content".equals(new String(zip.getInputStream(entry).readAllBytes(), StandardCharsets.UTF_8)), "Export contents changed");
                    BridgeGameTest.check(zip.getEntry(save.getFileName() + "/level.dat") != null, "Missing level.dat in export");
                }
                // Paused backup must fail immediately, without disabling autosave or making #2.
                context.runOnClient(client -> client.pauseGame(false));
                context.waitFor(client -> client.isPaused());
                console(process, "!!pb make paused-must-not-create");
                context.waitFor(client -> contains(log, "World paused; resume the game") || contains(log, "world paused"), 800);
                context.runOnClient(client -> client.gui.setScreen(null));
                context.waitFor(client -> !client.isPaused());
                // Reload cascades to the dependent adapter through MCDR's dependency manager.
                console(process, "!!MCDR plugin reload prime_backup");
                context.waitFor(client -> contains(log, "Plugin singleplayer_prime_backup@0.5.1 reloaded"), 1200);
                // A detached running world must never become an offline restore target.
                console(process, "!!MCDR server stop");
                context.waitFor(client -> contains(log, "Server process stopped with code 0"), 800);
                console(process, "!!pb back 1 --confirm");
                context.waitFor(client -> contains(log, "World session.lock is still held"), 800);
                BridgeGameTest.check(context.computeOnClient(client -> client.level != null), "Detach unexpectedly closed the game world");
                world.getServer().runCommand("setblock 2 -60 2 minecraft:gold_block");
                world.getServer().runCommand("item replace entity @a hotbar.0 with minecraft:gold_ingot 3");
                Files.writeString(save.resolve("bridge-test-marker.txt"), "changed-after-backup", StandardCharsets.UTF_8);
                final int before = count(log, "Singleplayer world ready");
                console(process, "!!MCDR server start");
                context.waitFor(client -> count(log, "Singleplayer world ready") > before, 1200);
                if (System.getProperty("os.name").startsWith("Windows")) {
                    fileHolder = new ProcessBuilder(python, "-c",
                            "import sys; f=open(sys.argv[1]); print('held',flush=True); sys.stdin.readline(); f.close()", heldConfig.toString())
                            .redirectErrorStream(true).start();
                    BridgeGameTest.check(fileHolder.getInputStream().readNBytes(4).length == 4, "Could not hold test file");
                }
                context.runOnClient(client -> client.player.connection.sendChat("!!pb back 1"));
                context.waitFor(client -> messages.stream().anyMatch(s -> s.contains("Please choose within") && s.contains("Confirm restore")), 800);
                context.runOnClient(client -> client.player.connection.sendChat("!!pb confirm"));
                if (fileHolder != null) {
                    BridgeGameTest.awaitAsyncClose(context, closeTasks, client -> client.level == null
                            && RestoreProgressMonitor.instance.current() != null
                            && RestoreProgressMonitor.instance.current().status().equals("failed"), 1800);
                    BridgeGameTest.check(contains(log, "syncmatica/config.json"), "Occupied file was not identified");
                    BridgeGameTest.check(!RestoreProgressMonitor.instance.current().modified(), "Preflight failure marked the world as modified");
                    BridgeGameTest.check(!RestoreProgressMonitor.blocks(save.getFileName().toString()), "Unmodified world remained locked after a preflight failure");
                    BridgeGameTest.check("changed-after-backup".equals(Files.readString(save.resolve("bridge-test-marker.txt"))), "Failed preflight partially deleted the world");
                    context.waitTicks(5);
                    context.takeScreenshot("prime-backup-locked-file-failed-return-menu");
                    context.clickScreenButton("mcdr-singleplayer.restore.button.menu");
                    context.waitFor(client -> !RestoreProgressMonitor.hasVisibleProgress(), 200);
                    BridgeGameTest.check(context.computeOnClient(client -> net.fabricmc.fabric.api.client.screen.v1.Screens.getWidgets(client.gui.screen()).stream()
                            .anyMatch(widget -> widget.visible && widget.active)), "Main menu buttons did not return after failed restore dismissal");
                    fileHolder.getOutputStream().write('\n');
                    fileHolder.getOutputStream().flush();
                    Process reader = fileHolder;
                    context.waitFor(client -> !reader.isAlive(), 800);
                    BridgeGameTest.check(reader.exitValue() == 0, "Reader did not release the file");
                    // Explorer can keep a child directory open with DELETE sharing;
                    // individual file probes pass, but moving its parent is denied.
                    fileHolder = new ProcessBuilder(python, "-c",
                            "import ctypes,sys; from ctypes import wintypes; k=ctypes.WinDLL('kernel32',use_last_error=True); "
                            + "k.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]; "
                            + "k.CreateFileW.restype=wintypes.HANDLE; k.CloseHandle.argtypes=[wintypes.HANDLE]; "
                            + "h=k.CreateFileW(sys.argv[1],1,7,None,3,0x02000000,None); assert h != ctypes.c_void_p(-1).value; "
                            + "print('held',flush=True); sys.stdin.readline(); k.CloseHandle(h)", heldConfig.getParent().toString())
                            .redirectErrorStream(true).start();
                    BridgeGameTest.check(fileHolder.getInputStream().readNBytes(4).length == 4, "Could not hold test directory");
                    console(process, "!!pb back 1 --confirm");
                    context.waitFor(client -> RestoreProgressMonitor.instance.current() != null
                            && RestoreProgressMonitor.instance.current().status().equals("failed")
                            && RestoreProgressMonitor.instance.current().detail().contains("File Explorer"), 1800);
                    BridgeGameTest.check(!RestoreProgressMonitor.instance.current().modified(), "Failed directory move marked the world as modified");
                    BridgeGameTest.check(!RestoreProgressMonitor.blocks(save.getFileName().toString()), "Failed directory move permanently locked the intact world");
                    BridgeGameTest.check("changed-after-backup".equals(Files.readString(save.resolve("bridge-test-marker.txt"))), "Failed directory move changed original files");
                    fileHolder.getOutputStream().write('\n');
                    fileHolder.getOutputStream().flush();
                    Process directoryReader = fileHolder;
                    context.waitFor(client -> !directoryReader.isAlive(), 800);
                    BridgeGameTest.check(directoryReader.exitValue() == 0, "Directory handle did not close");
                    // Older PB versions can leave a partial world after shutil.move
                    // falls back to copy/rmtree. A verified restore must still work
                    // even if this bound world's level.dat is already missing.
                    Files.delete(save.resolve("level.dat"));
                    console(process, "!!pb back 1 --confirm");
                }
                BridgeGameTest.awaitAsyncClose(context, closeTasks, client -> client.level == null && contains(log, "Restore to backup #1 done"), 1800);
                context.waitFor(client -> client.gui.screen() instanceof net.minecraft.client.gui.screens.TitleScreen && RestoreProgressMonitor.instance.current() != null && RestoreProgressMonitor.instance.current().status().equals("completed"), 800);
                BridgeGameTest.check(contains(log, "Creating backup of existing files"), "Missing pre-restore backup");
                BridgeGameTest.check(contains(log, "World closed; control session ended"), "Restore did not wait for a saved world shutdown");
                BridgeGameTest.check("original-backup-content".equals(Files.readString(save.resolve("bridge-test-marker.txt"))), "Restored file differs from backup");
                context.takeScreenshot("prime-backup-world-closed-for-restore");
                // Reopen the restored save, then verify chunk data and singleplayer inventory.
                var reopened = world.getWorldSave().open();
                try {
                    BridgeGameTest.check(reopened.getServer().computeOnServer(server -> server.overworld().getBlockState(new BlockPos(2, -60, 2)).is(Blocks.DIAMOND_BLOCK)), "Block did not roll back");
                    BridgeGameTest.check(reopened.getServer().computeOnServer(server -> {
                        var item = server.getPlayerList().getPlayerByName(player).getInventory().getItem(0);
                        return item.is(Items.DIAMOND) && item.getCount() == 7;
                    }), "Singleplayer inventory did not roll back");
                    final int beforeReconnect = count(log, "Singleplayer world ready");
                    console(process, "!!MCDR server start");
                    context.waitFor(client -> count(log, "Singleplayer world ready") > beforeReconnect, 1200);
                    context.runOnClient(client -> client.player.connection.sendChat("!!pb show 1"));
                    context.takeScreenshot("prime-backup-restored-diamond-world");
                } finally { reopened.close(); }
            }
            console(process, baseline ? "!!MCDR server stop_exit" : "!!MCDR server exit");
            Process active = process;
            context.waitFor(client -> !active.isAlive(), 800);
            BridgeGameTest.check(process.exitValue() == 0, "Prime Backup MCDR exit failed: " + log);
        } catch (IOException e) { throw new AssertionError(e); }
        finally {
            if (fileHolder != null && fileHolder.isAlive()) fileHolder.destroyForcibly();
            BridgeGameTest.mainBridge().setTestCloseDispatcher(null);
            if (process != null && process.isAlive()) {
                process.descendants().forEach(child -> child.destroyForcibly());
                process.destroy();
                try { if (!process.waitFor(5, TimeUnit.SECONDS)) process.destroyForcibly(); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            }
            if (context.computeOnClient(client -> client.level != null)) world.close();
        }
    }

    static boolean contains(Path path, String text) {
        try { return Files.exists(path) && Files.readString(path).contains(text); }
        catch (IOException e) { return false; }
    }

    static void checkConfluxNativeCache(Path game, Path save) {
        if (!FabricLoader.getInstance().isModLoaded("confluxmap")) return;
        try {
            Class<?> library = Class.forName("cn.net.rms.confluxmap.nativepredict.NativeLib");
            BridgeGameTest.check(Boolean.TRUE.equals(library.getMethod("available").invoke(null)), "Conflux Map native prediction did not load");
            try (var files = Files.walk(ConfluxNativeCache.directory(game))) {
                BridgeGameTest.check(files.anyMatch(path -> path.getFileName().toString().endsWith(".dll")
                        || path.getFileName().toString().endsWith(".so") || path.getFileName().toString().endsWith(".dylib")), "Native library was not cached outside saves");
            }
            if (save != null) BridgeGameTest.check(!Files.exists(save.resolve("confluxmap/natives")), "Conflux Map still cached native libraries inside the world");
        } catch (Exception e) { throw new AssertionError("Conflux Map native-cache compatibility failed", e); }
    }

    static int count(Path path, String text) {
        try { return Files.readString(path).split(java.util.regex.Pattern.quote(text), -1).length - 1; }
        catch (IOException e) { return 0; }
    }

    static void console(Process process, String command) throws IOException {
        process.getOutputStream().write((command + "\n").getBytes(StandardCharsets.UTF_8));
        process.getOutputStream().flush();
    }
}
