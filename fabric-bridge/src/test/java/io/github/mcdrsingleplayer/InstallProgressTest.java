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
        assertFalse(feedback.shouldOpen(failed, true));
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

    @Test void deferredWindowOpensOnceAndClosingDoesNotSilenceChatOrReopenIt() {
        var feedback = new InstallProgress.Feedback();
        var dependencies = new InstallProgress("dependencies", 1);
        assertFalse(feedback.shouldOpen(dependencies, false));
        assertTrue(feedback.shouldOpen(dependencies, true));
        assertFalse(feedback.shouldOpen(dependencies, true));
        assertTrue(feedback.shouldAnnounce(dependencies, 1000));
        assertFalse(feedback.shouldAnnounce(dependencies, 1500));
        assertTrue(feedback.shouldAnnounce(dependencies, 21000));
        var fallback = new InstallProgress("dependencies", 2);
        assertTrue(feedback.shouldAnnounce(fallback, 22000));
        var ready = new InstallProgress("ready", 0);
        assertTrue(feedback.shouldAnnounce(ready, 23000));
        assertFalse(feedback.shouldAnnounce(ready, 24000));
        assertFalse(feedback.shouldOpen(new InstallProgress("starting", 0), true));
        assertFalse(feedback.shouldAnnounce(dependencies, 45000));
    }

    @Test void existingReadyInstallationIsQuietAndFailureIsExplicitWithoutRepeatedPopups() {
        var existing = new InstallProgress.Feedback();
        assertFalse(existing.shouldAnnounce(new InstallProgress("ready", 0), 0));
        assertFalse(existing.shouldOpen(new InstallProgress("ready", 0), true));
        var feedback = new InstallProgress.Feedback();
        var failed = new InstallProgress("failed", 0);
        assertTrue(feedback.shouldOpen(failed, true));
        assertTrue(feedback.shouldAnnounce(failed, 0));
        assertFalse(feedback.shouldAnnounce(failed, 30000));
        assertFalse(feedback.shouldOpen(failed, true));
        assertFalse(failed.running());
    }
}
