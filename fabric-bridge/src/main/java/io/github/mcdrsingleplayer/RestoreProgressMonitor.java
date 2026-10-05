package io.github.mcdrsingleplayer;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/** Reads the local atomic status off the render thread; retains the last world session. */
public final class RestoreProgressMonitor implements AutoCloseable {
    static volatile RestoreProgressMonitor instance;
    private final Path path;
    private final Path lockPath;
    private final Set<String> lockedWorlds = java.util.concurrent.ConcurrentHashMap.newKeySet();
    private final java.util.Map<String, String> operationLocks = new java.util.HashMap<>();
    private final java.util.concurrent.ScheduledExecutorService reader;
    private volatile String session;
    private volatile Progress current;
    private volatile Progress latest;
    private volatile String dismissed;

    public record Progress(String operation, String session, String world, int backup, String stage,
            String status, String detail, long started, long backendPid, boolean modified) {
        boolean running() { return status.equals("running"); }
        boolean blocksWorld() { return running() || status.equals("failed") && modified; }
    }

    RestoreProgressMonitor(Path path) {
        this(path, path.getParent());
    }

    RestoreProgressMonitor(Path path, Path persistenceRoot) {
        this.path = path;
        lockPath = persistenceRoot.resolve(".mcdr_restore_locks.json");
        try {
            for (Path source : new java.util.LinkedHashSet<>(java.util.List.of(lockPath, path.resolveSibling(".mcdr_restore_locks.json")))) {
                if (!Files.isRegularFile(source) || Files.size(source) > 65536) continue;
                for (var world : JsonParser.parseString(Files.readString(source)).getAsJsonArray()) {
                    String name = world.getAsString();
                    if (!name.isEmpty() && name.length() <= 255) lockedWorlds.add(name);
                }
            }
        } catch (Exception ignored) { /* A valid progress file can also rebuild the lock. */ }
        instance = this;
        reader = Executors.newSingleThreadScheduledExecutor(action -> {
            var thread = new Thread(action, "mcdr-restore-status");
            thread.setDaemon(true);
            return thread;
        });
        reader.scheduleWithFixedDelay(this::poll, 0, 100, TimeUnit.MILLISECONDS);
    }

    void session(String value) {
        session = value;
        current = null;
        dismissed = null;
    }

    void closingWorld(String world, String value) {
        if (current == null || !current.running()) {
            current = new Progress("pending", value, Path.of(world).getFileName().toString(),
                0, "saving", "running", "", System.currentTimeMillis(), 0, false);
            latest = current;
        }
    }

    Progress current() { return current; }
    Progress visible() {
        Progress value = current;
        return value != null && !value.operation().equals(dismissed) ? value : null;
    }
    void dismiss() { if (current != null && !current.running()) dismissed = current.operation(); }

    public static boolean blocks(String world) {
        RestoreProgressMonitor monitor = instance;
        if (monitor == null) return false;
        // This check happens before opening session.lock or reading level.dat.
        monitor.poll();
        Progress value = monitor.latest;
        return monitor.lockedWorlds.contains(world) || value != null && value.world().equals(world) && value.blocksWorld();
    }

    public static boolean hasVisibleProgress() {
        RestoreProgressMonitor monitor = instance;
        return monitor != null && monitor.visible() != null;
    }

    public static void showBlocked(String world) {
        if (instance != null) {
            instance.dismissed = null;
            Progress value = instance.latest;
            if (value != null && value.world().equals(world) && value.blocksWorld()) instance.current = value;
            else instance.current = new Progress(java.util.UUID.randomUUID().toString().replace("-", ""), "", world,
                0, "failed", "failed", "", System.currentTimeMillis(), 0, true);
        }
        net.minecraft.client.Minecraft.getInstance().gui.setScreen(new net.minecraft.client.gui.screens.TitleScreen());
    }

    private synchronized void poll() {
        try {
            if (!Files.isRegularFile(path) || Files.size(path) > 16384) return;
            Progress value = parse(Files.readString(path), null);
            if (value == null) return;
            if (value.running() && value.backendPid() > 0 && !ProcessHandle.of(value.backendPid()).map(ProcessHandle::isAlive).orElse(false)) {
                value = new Progress(value.operation(), value.session(), value.world(), value.backup(), "failed", "failed",
                    "mcdr-singleplayer.restore.detail.interrupted", value.started(), value.backendPid(), value.modified());
            }
            latest = value;
            boolean previouslyLocked = lockedWorlds.contains(value.world());
            boolean changed = false;
            if (value.status().equals("completed")) {
                changed = lockedWorlds.remove(value.world());
                operationLocks.remove(value.world());
            } else if (value.modified() && lockedWorlds.add(value.world())) {
                changed = true;
                if (value.running()) operationLocks.put(value.world(), value.operation());
            } else if (!value.running() && !value.modified()
                    && value.operation().equals(operationLocks.get(value.world()))) {
                // A failed atomic rename proves this operation never moved the
                // world. Only undo its own provisional lock, never an older one.
                changed = lockedWorlds.remove(value.world());
                operationLocks.remove(value.world());
            }
            if (changed) saveLocks();
            if (session == null && !value.blocksWorld() && !previouslyLocked) return;
            if (session != null && !session.equals(value.session()) && !previouslyLocked) return;
            current = value;
        } catch (Exception ignored) { /* Keep the last valid state while a file is replaced. */ }
    }

    private void saveLocks() {
        Path temporary = lockPath.resolveSibling(lockPath.getFileName() + ".tmp");
        try {
            Files.createDirectories(lockPath.getParent());
            var records = new com.google.gson.JsonArray();
            lockedWorlds.stream().sorted().forEach(records::add);
            Files.writeString(temporary, records.toString());
            Files.move(temporary, lockPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception ignored) { /* The in-memory lock remains; PB owns the restore status. */ }
    }

    static Progress parse(String data, String session) {
        JsonObject record = JsonParser.parseString(data).getAsJsonObject();
        if (record.get("protocol").getAsInt() != 1) return null;
        String recordSession = record.get("session").getAsString();
        if (session != null && !session.equals(recordSession)) return null;
        String operation = record.get("operation").getAsString();
        String status = record.get("status").getAsString();
        String stage = record.get("stage").getAsString();
        String world = record.get("world_name").getAsString();
        String detail = record.get("detail").getAsString();
        if (!operation.matches("[a-f0-9]{32}") || world.length() > 255 || detail.length() > 512
                || !Set.of("running", "completed", "failed", "cancelled").contains(status)
                || !Set.of("checking", "saving", "waiting_files", "safety_backup", "restoring", "rolling_back", "player_data", "completed", "failed", "cancelled").contains(stage)) return null;
        int backup = record.get("backup_id").isJsonNull() ? 0 : record.get("backup_id").getAsInt();
        return new Progress(operation, recordSession, world, backup, stage, status, detail,
            record.get("started_at").getAsLong(), record.get("backend_pid").getAsLong(),
            record.has("modified") && record.get("modified").getAsBoolean());
    }

    @Override public void close() { reader.shutdownNow(); }
}
