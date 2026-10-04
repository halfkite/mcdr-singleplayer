package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class BridgeConfigTest {
    @TempDir Path game;

    private Path legacy() throws Exception {
        Path path = game.resolve("config/mcdr_singleplayer_bridge.json");
        BridgeConfig.load(path);
        return path;
    }

    @Test void freshConfigExistsOnlyInDedicatedRoot() throws Exception {
        var config = BridgeConfig.loadForGame(game);
        assertEquals(64, config.token.length());
        Path path = game.resolve("mcdr-singleplayer/mcdr-singleplayer-config.yml");
        assertTrue(Files.isRegularFile(path));
        assertTrue(Files.isDirectory(game.resolve("mcdr-singleplayer/plugindata")));
        assertFalse(Files.exists(game.resolve("mcdr-singleplayer/date")));
        assertTrue(Files.readString(path).contains("# 随机身份验证令牌，请勿分享或公开"));
        assertFalse(Files.exists(game.resolve("config")));
    }

    @Test void pythonOnboardingPreferencesSurviveClientRestart() throws Exception {
        var initial = BridgeConfig.loadForGame(game);
        Path path = BridgeConfig.pathForGame(game);
        String saved = Files.readString(path).replace("onboardingDismissed: false", "onboardingDismissed: true")
                .replace("onboardingLastClientId: \"\"", "onboardingLastClientId: \"last-client\"");
        Files.writeString(path, saved);
        var reopened = BridgeConfig.loadForGame(game);
        assertTrue(reopened.onboardingDismissed);
        assertEquals("last-client", reopened.onboardingLastClientId);
        assertEquals(initial.token, reopened.token);
        assertTrue(Files.readString(path).contains("onboardingDismissed: true"));
    }

    @Test void previousRuntimeConfigMovesToSharedRootAndKeepsToken() throws Exception {
        Path root = game.resolve("mcdr-singleplayer");
        Path previous = root.resolve("runtime/config");
        BridgeConfig old = BridgeConfig.load(previous.resolve("config.json"));
        Files.createDirectories(previous.resolve("plugins"));
        Files.writeString(previous.resolve("plugins/probe.py"), "plugin");
        Files.writeString(previous.resolve("config.yml"), "user-config");
        Files.writeString(previous.resolve("permission.yml"), "owner");
        var current = BridgeConfig.loadForGame(game);
        assertEquals(old.token, current.token);
        assertFalse(Files.exists(previous));
        assertEquals("plugin", Files.readString(root.resolve("plugins/probe.py")));
        assertEquals("owner", Files.readString(root.resolve("permission.yml")));
        assertEquals("user-config", Files.readString(root.resolve("config.yml")));
        assertEquals(old.token, BridgeConfig.loadForGame(game).token);
    }

    @Test void legacyConfigAndRestoreLocksMoveWithoutChangingToken() throws Exception {
        Path previous = legacy();
        var old = JsonParser.parseString(Files.readString(previous)).getAsJsonObject();
        Path common = game.resolve("mcdr2"); Files.createDirectories(common);
        old.addProperty("mcdrDirectory", common.toString());
        Files.writeString(previous, old.toString());
        Files.writeString(game.resolve("config/.mcdr_restore_locks.json"), "[\"Old World\"]");
        var config = BridgeConfig.loadForGame(game);
        assertEquals(old.get("token").getAsString(), config.token);
        assertFalse(Files.exists(previous));
        assertFalse(Files.exists(game.resolve("config/.mcdr_restore_locks.json")));
        Path root = game.resolve("mcdr-singleplayer");
        assertEquals("[\"Old World\"]", Files.readString(root.resolve("runtime/.mcdr_restore_locks.json")));
        assertFalse(Files.readString(BridgeConfig.pathForGame(game)).contains("mcdrDirectory"));
        try (var archived = Files.list(root.resolve("runtime/migration-history"))) {
            assertTrue(archived.findAny().isPresent());
        }
        assertEquals(common.toString(), JsonParser.parseString(Files.readString(root.resolve("runtime/.legacy-layout.json"))).getAsJsonObject().get("source").getAsString());
    }

    @Test void oldSharedRootSettingsAndProfilesMoveIntoGroups() throws Exception {
        Path root = game.resolve("mcdr-singleplayer");
        Files.createDirectories(root.resolve("data/Old World"));
        Files.writeString(root.resolve("config.json"), "{\"enabled\":true,\"port\":25591,\"token\":\"" + "a".repeat(64) + "\"}");
        Files.writeString(root.resolve("config.yml"), "language: en_us\n");
        Files.writeString(root.resolve("data/Old World/keep.txt"), "profile");
        var config = BridgeConfig.loadForGame(game);
        assertEquals(25591, config.port);
        assertEquals("language: en_us\n", Files.readString(root.resolve("config.yml")));
        assertEquals("profile", Files.readString(root.resolve("plugindata/Old World/keep.txt")));
        assertFalse(Files.exists(root.resolve("config.json")));
        assertTrue(Files.readString(root.resolve("mcdr-singleplayer-config.yml")).contains("port: 25591"));
        try (var archived = Files.list(root.resolve("runtime/migration-history"))) {
            assertEquals(1, archived.count());
        }
        assertFalse(Files.exists(root.resolve("data")));
    }

    @Test void oldDateProfilesMoveIntoPluginDataAndPreserveCollisions() throws Exception {
        Path root = game.resolve("mcdr-singleplayer");
        Path oldProfile = root.resolve("date/World");
        Path currentProfile = root.resolve("plugindata/World");
        Files.createDirectories(oldProfile);
        Files.createDirectories(currentProfile);
        Files.writeString(oldProfile.resolve("same.txt"), "same");
        Files.writeString(currentProfile.resolve("same.txt"), "same");
        Files.writeString(oldProfile.resolve("conflict.txt"), "old data");
        Files.writeString(currentProfile.resolve("conflict.txt"), "current data");
        Files.writeString(oldProfile.resolve("only-old.txt"), "keep this");

        BridgeConfig.loadForGame(game);

        assertFalse(Files.exists(root.resolve("date")));
        assertEquals("same", Files.readString(currentProfile.resolve("same.txt")));
        assertEquals("current data", Files.readString(currentProfile.resolve("conflict.txt")));
        assertEquals("keep this", Files.readString(currentProfile.resolve("only-old.txt")));
        try (var archived = Files.list(root.resolve("runtime/migration-history"))) {
            assertEquals(1, archived.filter(path -> path.getFileName().toString().endsWith("-conflict.txt")).count());
        }
    }

    @Test void liveOldRestoreBlocksMigrationBeforeAnyFilesMove() throws Exception {
        Path previous = legacy();
        String original = Files.readString(previous);
        Files.writeString(game.resolve("config/.mcdr_restore_progress.json"), "{\"status\":\"running\",\"backend_pid\":" + ProcessHandle.current().pid() + "}");
        assertThrows(java.io.IOException.class, () -> BridgeConfig.loadForGame(game));
        assertEquals(original, Files.readString(previous));
        assertFalse(Files.exists(BridgeConfig.pathForGame(game)));
    }

    @Test void existingSettingsWinAndFailedRestoreLocksAreMerged() throws Exception {
        legacy();
        Path path = BridgeConfig.pathForGame(game);
        var current = BridgeConfig.load(path);
        current.port = 25590;
        Files.writeString(path, new com.google.gson.Gson().toJson(current));
        Files.createDirectories(path.getParent().resolve("runtime"));
        Files.writeString(path.getParent().resolve("runtime/.mcdr_restore_locks.json"), "[\"New World\"]");
        Files.writeString(game.resolve("config/.mcdr_restore_locks.json"), "[\"Old World\"]");
        assertEquals(25590, BridgeConfig.loadForGame(game).port);
        var locks = JsonParser.parseString(Files.readString(path.getParent().resolve("runtime/.mcdr_restore_locks.json"))).getAsJsonArray();
        assertEquals(2, locks.size());
        assertFalse(Files.exists(game.resolve("config/mcdr_singleplayer_bridge.json")));
    }
}
