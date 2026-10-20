package io.github.mcdrsingleplayer;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/**
 * Whether MCDR itself is installed for this game instance, published per client launch so the
 * menu can offer the download and the controller starts only when the user asked for it.
 */
final class McdrSetup {
    static final String READY = "ready";
    /** Python itself is missing, so MCDR cannot be installed until the player installs it. */
    static final String PYTHON_MISSING = "python";

    private final Path statusFile;
    private volatile String published = "";
    private volatile String reason = "";
    private volatile boolean actionNeeded;
    private volatile boolean running;

    McdrSetup(Path statusFile) {
        this.statusFile = statusFile;
    }

    /** Visible setup reason; empty while the launch is still checking the installed runtime. */
    String reason() { return reason; }

    boolean actionNeeded() { return actionNeeded && !running; }
    boolean running() { return running; }

    void check(String reason) {
        running = false;
        this.reason = reason;
        actionNeeded = !reason.isEmpty() && !READY.equals(reason);
    }

    /** Installs MCDR after the user accepted the download from the main menu. */
    void installing() {
        running = true;
        actionNeeded = false;
    }

    void write() {
        String data = "{\"protocol\":1,\"reason\":\"" + reason + "\",\"running\":" + running + "}";
        // The probe re-checks every few seconds; an unchanged state needs no disk write at all.
        if (data.equals(published)) return;
        try {
            Files.createDirectories(statusFile.getParent());
            Path temporary = statusFile.resolveSibling(statusFile.getFileName() + ".tmp");
            Files.writeString(temporary, data, StandardCharsets.UTF_8);
            Files.move(temporary, statusFile, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            published = data;
        } catch (IOException ignored) { /* The next check republishes the state. */ }
    }
}
