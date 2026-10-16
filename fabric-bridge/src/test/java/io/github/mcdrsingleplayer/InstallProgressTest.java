package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class InstallProgressTest {
    @Test void unexpectedDisconnectAfterReadyAnnouncesFailureOnce() {
        var feedback = new InstallProgress.Feedback();
        assertFalse(feedback.shouldAnnounce(new InstallProgress("ready", 0), 1000));
        var failed = new InstallProgress("failed", 0);
        assertTrue(feedback.shouldAnnounce(failed, 2000));
        assertFalse(feedback.shouldAnnounce(failed, 23000));
        assertFalse(failed.running());
    }

    @Test void ignoresPreviousLaunchAndMalformedOrUnknownStages() {
        String status = "{\"protocol\":1,\"client_id\":\"current\",\"stage\":\"dependencies\",\"attempt\":2}";
        assertEquals(new InstallProgress("dependencies", 2), InstallProgress.parse(status, "current"));
        assertNull(InstallProgress.parse(status, "other-launch"));
        assertNull(InstallProgress.parse("partial JSON", "current"));
        assertNull(InstallProgress.parse(status.replace("dependencies", "unknown"), "current"));
        assertNull(InstallProgress.parse(status.replace("dependencies", "ready"), "current"));
        assertNull(InstallProgress.parse(status.replace("\"attempt\":2", "\"attempt\":-1"), "current"));
    }

    @Test void announcesStageChangesAndRemindsAtMostEveryTwentySeconds() {
        var feedback = new InstallProgress.Feedback();
        var dependencies = new InstallProgress("dependencies", 1);
        assertTrue(feedback.shouldAnnounce(dependencies, 1000));
        assertFalse(feedback.shouldAnnounce(dependencies, 1500));
        assertTrue(feedback.shouldAnnounce(dependencies, 21000));
        var fallback = new InstallProgress("dependencies", 2);
        assertTrue(feedback.shouldAnnounce(fallback, 22000));
        var ready = new InstallProgress("ready", 0);
        assertTrue(feedback.shouldAnnounce(ready, 23000));
        assertFalse(feedback.shouldAnnounce(ready, 24000));
        // A finished installation never repeats, and no world re-entry can restart the reminders.
        assertFalse(feedback.shouldAnnounce(new InstallProgress("starting", 0), 45000));
        assertFalse(feedback.shouldAnnounce(dependencies, 65000));
    }

    @Test void aRunningControllerNeverRepeatsStartupChatInsideAWorld() {
        var feedback = new InstallProgress.Feedback();
        var starting = new InstallProgress("starting", 0);
        // The real log showed this exact line repeating every 20 seconds for five minutes.
        for (long now = 0; now < 600_000; now += 20_000) {
            assertFalse(feedback.shouldAnnounceInstallation(starting, now), "starting repeated at " + now);
        }
        assertFalse(feedback.shouldAnnounceInstallation(new InstallProgress("waiting_instance", 0), 0),
                "waiting_instance is not installation work");
        assertFalse(feedback.shouldAnnounceInstallation(new InstallProgress("ready", 0), 0),
                "An already prepared runtime must stay quiet");
        assertTrue(starting.running(), "The controller is still running even though it is not installing");
        assertFalse(starting.installing());
    }

    @Test void realInstallationWorkStillReportsItsStages() {
        var feedback = new InstallProgress.Feedback();
        assertTrue(feedback.shouldAnnounceInstallation(new InstallProgress("preparing", 0), 0));
        assertTrue(feedback.shouldAnnounceInstallation(new InstallProgress("dependencies", 1), 1000));
        assertFalse(feedback.shouldAnnounceInstallation(new InstallProgress("dependencies", 1), 5000));
        assertTrue(feedback.shouldAnnounceInstallation(new InstallProgress("dependencies", 1), 21000));
        assertTrue(feedback.shouldAnnounceInstallation(new InstallProgress("failed", 0), 22000));
        // Once the controller is up, nothing more is announced about installation.
        assertFalse(feedback.shouldAnnounceInstallation(new InstallProgress("starting", 0), 23000));
    }

    @Test void existingReadyInstallationIsQuietAndFailureIsExplicit() {
        var existing = new InstallProgress.Feedback();
        assertFalse(existing.shouldAnnounce(new InstallProgress("ready", 0), 0));
        var feedback = new InstallProgress.Feedback();
        var failed = new InstallProgress("failed", 0);
        assertTrue(feedback.shouldAnnounce(failed, 0));
        assertFalse(feedback.shouldAnnounce(failed, 30000));
    }
}
