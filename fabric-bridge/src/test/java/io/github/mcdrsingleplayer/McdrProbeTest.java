package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;

import com.google.gson.JsonObject;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * The startup probe decides what the main menu offers. A marker that does not record the adapted
 * release must ask for a download; the earlier build also reported a download reason while the
 * runtime was ready, so the menu asked for an update on every launch.
 */
class McdrProbeTest {
    /** The adapted release; the bundle declares the same value in bootstrap.py. */
    private static final String ADAPTED_MCDR = "2.16.0";

    @Test void anAbsentEnvironmentAsksForTheDownload(@TempDir Path game) throws Exception {
        assertEquals("missing", unpack(probe(game)).reason());
    }

    @Test void anEnvironmentWithoutAnInstallerMarkerAsksForTheDownload(@TempDir Path game) throws Exception {
        environment(game);
        var result = unpack(probe(game));
        assertFalse(result.ready());
        assertEquals("missing", result.reason());
    }

    @Test void anOlderMcdrReleaseAsksForAnUpdate(@TempDir Path game) throws Exception {
        Path common = environment(game);
        writeMarker(common, "2.15.0");
        var result = unpack(probe(game));
        assertFalse(result.ready());
        assertEquals("outdated", result.reason());
    }

    @Test void aMarkerThatRecordsTheAdaptedReleaseIsNotOutdated(@TempDir Path game) throws Exception {
        Path common = environment(game);
        writeMarker(common, ADAPTED_MCDR);
        // The environment has no real interpreter, so the deep check reports a broken runtime.
        // It must never report the stale-version reason that made every launch ask for an update.
        String reason = unpack(probe(game)).reason();
        assertNotEquals("outdated", reason, "A current marker must not report a stale release");
        assertNotEquals(McdrSetup.READY, reason);
    }

    private static Object probe(Path game) throws Exception {
        var runtime = new AutoRuntime(new BridgeConfig(), config(game), game);
        Method probe = AutoRuntime.class.getDeclaredMethod("probe");
        probe.setAccessible(true);
        return probe.invoke(runtime);
    }

    private record Result(boolean ready, String reason) { }

    /** The setup check is package private, so unpack it through its accessors. */
    private static Result unpack(Object check) throws Exception {
        Method ready = check.getClass().getDeclaredMethod("ready");
        Method reason = check.getClass().getDeclaredMethod("reason");
        ready.setAccessible(true);
        reason.setAccessible(true);
        return new Result((Boolean) ready.invoke(check), (String) reason.invoke(check));
    }

    private static Path config(Path game) {
        return game.resolve("mcdr-singleplayer/mcdr-singleplayer-config.yml");
    }

    private static Path environment(Path game) throws Exception {
        Path common = game.resolve("mcdr-singleplayer");
        Path python = common.resolve("runtime/.bridge-venv/Scripts/python.exe");
        Files.createDirectories(python.getParent());
        Files.writeString(python, "");
        return common;
    }

    private static void writeMarker(Path common, String mcdr) throws Exception {
        JsonObject marker = new JsonObject();
        marker.addProperty("mcdr", mcdr);
        Files.writeString(common.resolve("runtime/runtime-install.json"), marker.toString());
    }
}
