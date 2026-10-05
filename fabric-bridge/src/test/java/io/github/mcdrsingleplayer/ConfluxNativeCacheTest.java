package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class ConfluxNativeCacheTest {
    @Test void cacheIsStableInThisProcessAndOutsideSaveData() {
        Path game = Path.of("game");
        Path cache = ConfluxNativeCache.directory(game);
        assertEquals(cache, ConfluxNativeCache.directory(game));
        assertTrue(cache.startsWith(BridgeConfig.runtimeForGame(game)));
        assertFalse(cache.startsWith(game.resolve("saves")));
        assertFalse(cache.startsWith(game.resolve("mcdr-singleplayer/plugindata")));
        assertDoesNotThrow(() -> java.util.UUID.fromString(cache.getFileName().toString()));
    }
}
