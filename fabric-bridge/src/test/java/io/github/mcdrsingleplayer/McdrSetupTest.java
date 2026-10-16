package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class McdrSetupTest {
    @Test void aMissingRuntimeAsksForTheDownloadUntilItStarts() {
        var setup = new McdrSetup(Path.of("setup-status.json"));
        // Nothing is published before the first probe, so the menu must not offer anything yet.
        assertFalse(setup.actionNeeded());
        assertFalse(setup.running());
        assertEquals("", setup.reason());

        setup.check("missing");
        assertTrue(setup.actionNeeded());
        assertEquals("missing", setup.reason());

        setup.installing();
        assertTrue(setup.running());
        assertFalse(setup.actionNeeded(), "An install in progress must not offer a second download");
    }

    @Test void readyAndOutdatedStatesDriveThePrompt() {
        var setup = new McdrSetup(Path.of("setup-status.json"));
        // The waiting notice still needs the reason, otherwise the menu hides a required download.
        setup.check("");
        assertFalse(setup.actionNeeded());
        assertEquals("", setup.reason());

        for (String reason : new String[]{"missing", "outdated", "broken", "failed"}) {
            setup.check(reason);
            assertTrue(setup.actionNeeded(), reason + " must offer a download");
            assertEquals(reason, setup.reason());
        }

        setup.check(McdrSetup.READY);
        assertFalse(setup.actionNeeded(), "A ready runtime must not offer a download");
        assertEquals(McdrSetup.READY, setup.reason());
    }

    @Test void publishedStatusSurvivesAnAtomicReplacement(@TempDir Path directory) throws Exception {
        Path status = directory.resolve("clients/launch/setup-status.json");
        var setup = new McdrSetup(status);
        setup.check("outdated");
        setup.write();
        String data = Files.readString(status);
        assertTrue(data.contains("\"reason\":\"outdated\""), data);
        assertTrue(data.contains("\"running\":false"), data);

        setup.installing();
        setup.write();
        data = Files.readString(status);
        assertTrue(data.contains("\"reason\":\"outdated\""), data);
        assertTrue(data.contains("\"running\":true"), data);
        assertEquals(1, Files.list(directory.resolve("clients/launch")).filter(Files::isRegularFile).count(),
                "Temporary status files must not accumulate");
    }

    @Test void theMenuNeverClaimsToInstallSomethingThatIsAlreadyPrepared() {
        var setup = new McdrSetup(Path.of("setup-status.json"));
        // Before the first probe publishes anything the menu is still checking.
        assertEquals(McdrSetupScreen.Status.CHECKING, SingleplayerBridge.setupStatus(setup, progress("preparing")));

        for (String reason : new String[]{"missing", "outdated", "broken"}) {
            setup.check(reason);
            assertEquals(McdrSetupScreen.Status.NEEDS_INSTALL,
                    SingleplayerBridge.setupStatus(setup, progress("preparing")), reason);
        }

        setup.check("failed");
        assertEquals(McdrSetupScreen.Status.FAILED, SingleplayerBridge.setupStatus(setup, progress("preparing")));

        setup.check(McdrSetup.READY);
        assertEquals(McdrSetupScreen.Status.READY, SingleplayerBridge.setupStatus(setup, progress("ready")));

        // An install in progress reports its real stage, and a failure stays visible.
        setup.check("missing");
        setup.installing();
        for (String stage : new String[]{"preparing", "environment", "dependencies", "files", "config", "plugins"}) {
            assertEquals(McdrSetupScreen.Status.INSTALLING,
                    SingleplayerBridge.setupStatus(setup, progress(stage)), stage);
        }
        assertEquals(McdrSetupScreen.Status.FAILED, SingleplayerBridge.setupStatus(setup, progress("failed")));
        // The controller is already prepared while it waits for a world, so this is not "installing".
        assertEquals(McdrSetupScreen.Status.READY, SingleplayerBridge.setupStatus(setup, progress("starting")));
        assertEquals(McdrSetupScreen.Status.READY, SingleplayerBridge.setupStatus(setup, progress("ready")));
    }

    private static InstallProgress progress(String stage) {
        return new InstallProgress(stage, 0);
    }
}
