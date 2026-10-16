package io.github.mcdrsingleplayer;

import com.google.gson.JsonParser;
import java.util.Set;

/** Installer stages, scoped to this client launch rather than an old installation marker. */
record InstallProgress(String stage, int attempt) {
    private static final Set<String> STAGES = Set.of("preparing", "environment", "dependencies", "files",
            "config", "plugins", "waiting_instance", "starting", "ready", "failed");

    boolean running() { return !stage.equals("ready") && !stage.equals("failed"); }

    /** True only while MCDR is really being installed; startup stages are not installation work. */
    boolean installing() { return running() && !stage.equals("starting") && !stage.equals("waiting_instance"); }

    String translationKey() { return "mcdr-singleplayer.install.stage." + stage; }

    static InstallProgress parse(String data, String clientId) {
        try {
            var value = JsonParser.parseString(data).getAsJsonObject();
            if (value.get("protocol").getAsInt() != 1 || !clientId.equals(value.get("client_id").getAsString())) return null;
            String stage = value.get("stage").getAsString();
            int attempt = value.get("attempt").getAsInt();
            if (!STAGES.contains(stage) || stage.equals("ready") || attempt < 0 || attempt > 10) return null;
            return new InstallProgress(stage, attempt);
        } catch (RuntimeException ignored) { return null; }
    }

    /** Chat feedback only: the installer window is a menu-time prompt and never opens inside a world. */
    static final class Feedback {
        private boolean finished;
        private InstallProgress announced;
        private long lastAnnouncement;

        boolean shouldAnnounce(InstallProgress value, long now) {
            if (finished && !value.stage().equals("failed")) return false;
            if (value.stage().equals("ready")) {
                finished = true;
                return announced != null;
            }
            if (!value.equals(announced) || value.running() && now - lastAnnouncement >= 20000) {
                announced = value;
                lastAnnouncement = now;
                return true;
            }
            return false;
        }

        /**
         * Chat may only narrate real installation work. A controller that is starting or waiting for
         * another client is not progress inside a world, so it must not repeat on a timer.
         */
        boolean shouldAnnounceInstallation(InstallProgress value, long now) {
            return (value.installing() || value.stage().equals("failed")) && shouldAnnounce(value, now);
        }
    }
}
