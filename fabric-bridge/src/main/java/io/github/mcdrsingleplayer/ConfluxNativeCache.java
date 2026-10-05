package io.github.mcdrsingleplayer;

import java.nio.file.Path;
import java.util.UUID;

/** Native libraries stay loaded until JVM exit; keep them outside any save. */
public final class ConfluxNativeCache {
    private static final String SESSION = UUID.randomUUID().toString();
    private ConfluxNativeCache() {}

    public static Path directory(Path game) {
        return BridgeConfig.runtimeForGame(game).resolve("native-cache/confluxmap").resolve(SESSION);
    }
}
