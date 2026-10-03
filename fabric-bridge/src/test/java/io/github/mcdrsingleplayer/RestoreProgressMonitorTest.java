package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class RestoreProgressMonitorTest {
    @TempDir Path directory;
    private JsonObject status(String state, boolean modified) {
        var record = new JsonObject();
        record.addProperty("protocol", 1);
        record.addProperty("operation", "a".repeat(32));
        record.addProperty("session", "current-world");
        record.addProperty("world_name", "World");
        record.addProperty("backup_id", 7);
        record.addProperty("backend_pid", ProcessHandle.current().pid());
        record.addProperty("started_at", System.currentTimeMillis());
        record.addProperty("status", state);
        record.addProperty("stage", state.equals("running") ? "restoring" : state);
        record.addProperty("detail", "");
        record.addProperty("modified", modified);
        return record;
    }
    @Test void targetWorldStaysLockedUntilCompletionAndFailureCannotClaimSuccess() throws Exception {
        Path path = directory.resolve(".mcdr_restore_progress.json");
        try (var monitor = new RestoreProgressMonitor(path)) {
            monitor.session("current-world");
            Files.writeString(path, status("running", true).toString());
            assertTrue(RestoreProgressMonitor.blocks("World"));
            assertFalse(RestoreProgressMonitor.blocks("Other"));
            Files.writeString(path, status("failed", true).toString());
            assertTrue(RestoreProgressMonitor.blocks("World"));
            Files.writeString(path, status("completed", true).toString());
            assertFalse(RestoreProgressMonitor.blocks("World"));
            assertNotNull(monitor.visible());
            monitor.dismiss();
            assertNull(monitor.visible());
        }
    }
    @Test void otherSessionsAndInvalidStatesAreIgnored() {
        assertNull(RestoreProgressMonitor.parse(status("running", true).toString(), "another-world"));
        assertNull(RestoreProgressMonitor.parse(status("invented", true).toString(), "current-world"));
        var cancelled = RestoreProgressMonitor.parse(status("cancelled", false).toString(), "current-world");
        assertNotNull(cancelled);
        assertFalse(cancelled.blocksWorld());
    }
    @Test void chunkBackupRecoveryAndPlayerStagesKeepWorldLocked() throws Exception {
        Path path = directory.resolve(".mcdr_restore_progress.json");
        try (var monitor = new RestoreProgressMonitor(path)) {
            monitor.session("current-world");
            for (String stage : java.util.List.of("rolling_back", "player_data")) {
                var record = status("running", true);
                record.addProperty("stage", stage);
                record.add("backup_id", com.google.gson.JsonNull.INSTANCE);
                Files.writeString(path, record.toString());
                assertTrue(RestoreProgressMonitor.blocks("World"));
                assertEquals(stage, monitor.current().stage());
                assertEquals(0, monitor.current().backup());
            }
            Files.writeString(path, status("failed", true).toString());
            assertTrue(RestoreProgressMonitor.blocks("World"));
        }
    }
    @Test void deferredMigrationReadsBothLockFilesAndWritesOnlyToCanonicalRoot() throws Exception {
        Path legacy = directory.resolve("config/.mcdr_restore_progress.json");
        Files.createDirectories(legacy.getParent());
        Path root = directory.resolve("mcdr-singleplayer");
        Files.createDirectories(root);
        Files.writeString(legacy.resolveSibling(".mcdr_restore_locks.json"), "[\"Old World\"]");
        Files.writeString(root.resolve(".mcdr_restore_locks.json"), "[\"New World\"]");
        Files.writeString(legacy, status("running", true).toString());
        try (var monitor = new RestoreProgressMonitor(legacy, root)) {
            assertTrue(RestoreProgressMonitor.blocks("Old World"));
            assertTrue(RestoreProgressMonitor.blocks("New World"));
            assertTrue(RestoreProgressMonitor.blocks("World"));
            assertTrue(Files.readString(root.resolve(".mcdr_restore_locks.json")).contains("World"));
            assertEquals("[\"Old World\"]", Files.readString(legacy.resolveSibling(".mcdr_restore_locks.json")));
        }
    }
    @Test void interruptedRestoreLockSurvivesOtherWorldsRestartAndUnconfirmedRetry() throws Exception {
        Path path = directory.resolve(".mcdr_restore_progress.json");
        try (var monitor = new RestoreProgressMonitor(path)) {
            monitor.session("current-world");
            var failed = status("running", true);
            failed.addProperty("backend_pid", Long.MAX_VALUE);
            Files.writeString(path, failed.toString());
            assertTrue(RestoreProgressMonitor.blocks("World"));
            assertEquals("failed", monitor.current().status());
            monitor.session("other-world");
            Files.writeString(path, status("cancelled", false).toString());
            assertTrue(RestoreProgressMonitor.blocks("World"));
        }
        Files.delete(path);
        try (var monitor = new RestoreProgressMonitor(path)) {
            assertTrue(RestoreProgressMonitor.blocks("World"));
            assertFalse(RestoreProgressMonitor.blocks("Other"));
            Files.writeString(path, status("completed", true).toString());
            assertFalse(RestoreProgressMonitor.blocks("World"));
        }
    }
}
