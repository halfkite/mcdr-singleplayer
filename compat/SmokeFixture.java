package io.github.mcdrsingleplayer.smoke;

@IMPORTS@
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.world.level.*;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import net.minecraft.world.level.storage.LevelResource;

/** Test-only fixture: loads the merged distribution, uses disposable saves and stock PB. */
@ANNOTATION@
public final class SmokeFixture @INTERFACE@ {
    private int phase;
    private long started = System.currentTimeMillis();
    private Process mcdr;
    private Path save;
    private final Path game = Path.of(System.getProperty("mcdr.smoke.game"));
    private final Path log = game.resolve("prime-backup-smoke.log");
    private boolean observedLock;
    private boolean success;
    @REGISTRATION@

    private void tick(Minecraft client) {
        try {
            if (phase == 99) return;
            if (System.currentTimeMillis() - started > 240000) throw new AssertionError("Timed out at phase " + phase);
            if (phase >= 4 && phase <= 5) observedLock |= blocks();
            switch (phase) {
                case 0 -> {
                    if (!(@SCREEN@ instanceof TitleScreen) || @OVERLAY@ != null) return;
                    client.createWorldOpenFlows().createFreshLevel("matrix-smoke", @SETTINGS@,
                        new WorldOptions(1234L, false, false), WorldPresets::createNormalWorldDimensions, new TitleScreen());
                    advance(1);
                }
                case 1 -> {
                    if (client.player == null || client.level == null) return;
                    save = client.getSingleplayerServer().getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize();
                    Files.writeString(save.resolve("matrix-marker.txt"), "before-backup");
                    mcdr = new ProcessBuilder(System.getProperty("mcdr.smoke.python"), System.getProperty("mcdr.smoke.root") + "/scripts/prime_backup_game_harness.py",
                        "--game-dir", game.toString(), "--world-dir", save.toString(), "--player", client.player.getName().getString(),
                        "--prime-backup", System.getProperty("mcdr.smoke.pb"))
                        .redirectErrorStream(true).redirectOutput(log.toFile()).start();
                    advance(2);
                }
                case 2 -> {
                    if (!contains("Singleplayer world ready")) return;
                    var root = client.getConnection().getCommands().getRoot().getChild("!!pb");
                    if (root == null || root.getChild("make") == null) return;
                    note("command-tree: !!pb make registered");
                    client.player.connection.sendChat("!!pb make matrix-smoke");
                    advance(3);
                }
                case 3 -> {
                    if (!contains("Backup completed, ID") || System.currentTimeMillis() - started < 5000) return;
                    note("backup: completed");
                    Files.writeString(save.resolve("matrix-marker.txt"), "after-backup");
                    client.player.connection.sendChat("!!pb back 1");
                    advance(4);
                }
                case 4 -> {
                    if (!contains("Gonna restore the world") || System.currentTimeMillis() - started < 1500) return;
                    client.player.connection.sendChat("!!pb confirm");
                    advance(5);
                }
                case 5 -> {
                    if (client.level != null || !contains("Restore to backup #1 done")) return;
                    if (blocks()) return;
                    if (!observedLock) throw new AssertionError("Restore never locked the world");
                    if (!Files.readString(save.resolve("matrix-marker.txt")).equals("before-backup")) throw new AssertionError("Backup file was not restored");
                    if (!(@SCREEN@ instanceof TitleScreen)) return;
                    note("restore: title menu reached, world locked until complete, marker restored");
                    client.createWorldOpenFlows().openWorld("matrix-smoke", () -> {});
                    advance(6);
                }
                case 6 -> {
                    if (client.player == null) return;
                    note("reopen: restored world entered");
                    mcdr.getOutputStream().write("!!MCDR server exit\n".getBytes(StandardCharsets.UTF_8));
                    mcdr.getOutputStream().flush();
                    advance(7);
                }
                case 7 -> {
                    if (mcdr.isAlive()) return;
                    if (mcdr.exitValue() != 0) throw new AssertionError("MCDR process failed");
                    success = true;
                    Files.writeString(game.resolve("smoke-result.json"), "{\"success\":true,\"game\":\"@GAME@\",\"loader\":\"@LOADER@\",\"command_tree\":true,\"backup\":true,\"restore\":true,\"reopen\":true}");
                    note("PASS");
                    phase = 99;
                    client.stop();
                }
            }
        } catch (Throwable error) {
            error.printStackTrace();
            try { Files.writeString(game.resolve("smoke-result.json"), "{\"success\":false,\"phase\":" + phase + "}"); } catch (Exception ignored) {}
            if (mcdr != null && mcdr.isAlive()) mcdr.descendants().forEach(ProcessHandle::destroy);
            if (mcdr != null) mcdr.destroy();
            phase = 99;
            client.stop();
        }
    }

    private boolean blocks() throws Exception {
        String implementation = (String) Class.forName("io.github.mcdrsingleplayer.bootstrap.VersionSelector").getMethod("implementation").invoke(null);
        return (boolean) Class.forName(implementation + ".RestoreProgressMonitor").getMethod("blocks", String.class).invoke(null, "matrix-smoke");
    }
    private boolean contains(String text) throws Exception { return Files.exists(log) && Files.readString(log).contains(text); }
    private void advance(int value) throws Exception { phase = value; started = System.currentTimeMillis(); note("phase " + value); }
    private void note(String text) throws Exception { Files.writeString(game.resolve("smoke-events.log"), text + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND); }
}
