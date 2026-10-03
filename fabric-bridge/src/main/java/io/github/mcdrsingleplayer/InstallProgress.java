package io.github.mcdrsingleplayer;

import com.google.gson.JsonParser;
import java.util.Set;

/** Installer stages, scoped to this client launch rather than an old installation marker. */
record InstallProgress(String stage, int attempt) {
    private static final Set<String> STAGES = Set.of("preparing", "environment", "dependencies", "files",
            "config", "plugins", "starting", "ready", "failed");

    boolean running() { return !stage.equals("ready") && !stage.equals("failed"); }
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

    /** One dismissible window per world, with stage changes and slow-install reminders in chat. */
    static final class Feedback {
        private boolean shown;
        private boolean finished;
        private InstallProgress announced;
        private long lastAnnouncement;

        boolean shouldOpen(InstallProgress value, boolean available) {
            if (finished || value.stage().equals("ready")) { shown = true; return false; }
            if (shown || !available) return false;
            shown = true;
            return true;
        }

        boolean shouldAnnounce(InstallProgress value, long now) {
            if (finished) return false;
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
    }
}
