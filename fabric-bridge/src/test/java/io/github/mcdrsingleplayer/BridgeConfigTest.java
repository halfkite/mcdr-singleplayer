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
        assertTrue(Files.isRegularFile(game.resolve("mcdr-singleplayer/runtime/config/config.json")));
        assertFalse(Files.exists(game.resolve("config")));
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
        assertFalse(Files.readString(root.resolve("runtime/config/config.json")).contains("mcdrDirectory"));
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
        assertEquals("language: en_us\n", Files.readString(root.resolve("runtime/config/config.yml")));
        assertEquals("profile", Files.readString(root.resolve("date/Old World/keep.txt")));
        assertFalse(Files.exists(root.resolve("config.json")));
        assertFalse(Files.exists(root.resolve("data")));
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
        Files.writeString(path.getParent().getParent().resolve(".mcdr_restore_locks.json"), "[\"New World\"]");
        Files.writeString(game.resolve("config/.mcdr_restore_locks.json"), "[\"Old World\"]");
        assertEquals(25590, BridgeConfig.loadForGame(game).port);
        var locks = JsonParser.parseString(Files.readString(path.getParent().getParent().resolve(".mcdr_restore_locks.json"))).getAsJsonArray();
        assertEquals(2, locks.size());
        assertFalse(Files.exists(game.resolve("config/mcdr_singleplayer_bridge.json")));
    }
}
