package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AutoRuntimeTest {
    @TempDir Path game;

    @Test void lanGuestStartupAndExitCannotOverwriteTheHostsSession() throws Exception {
        var config = new BridgeConfig();
        var host = new AutoRuntime(config, BridgeConfig.pathForGame(game), game);
        host.publish("host-world", "host-session", "Host", "zh_cn", 25591);
        Path state;
        try (var files = Files.walk(BridgeConfig.runtimeForGame(game).resolve("clients"))) {
            state = files.filter(path -> path.getFileName().toString().equals("session.json")).findFirst().orElseThrow();
        }
        byte[] before = Files.readAllBytes(state);
        var guest = new AutoRuntime(config, BridgeConfig.pathForGame(game), game);
        guest.publish(null, null);
        guest.closing();
        assertArrayEquals(before, Files.readAllBytes(state));
        var session = JsonParser.parseString(Files.readString(state)).getAsJsonObject();
        assertEquals("host-session", session.get("session").getAsString());
        assertEquals(25591, session.get("bridge_port").getAsInt());
        assertFalse(session.get("closing").getAsBoolean());
        assertFalse(Files.exists(BridgeConfig.runtimeForGame(game).resolve(".mcdr_bridge_session.json")));
    }
}
