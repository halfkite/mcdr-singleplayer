package io.github.mcdrsingleplayer.bootstrap;

import com.google.gson.JsonParser;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/** Select an explicitly compiled implementation, never guess at future game APIs. */
public final class VersionSelector {
    public static String current() {
        try (var stream = VersionSelector.class.getResourceAsStream("/version.json")) {
            if (stream == null) return neoForgeVersion();
            return JsonParser.parseReader(new InputStreamReader(stream, StandardCharsets.UTF_8))
                .getAsJsonObject().get("id").getAsString();
        } catch (java.io.IOException exception) { throw new IllegalStateException(exception); }
    }

    private static String neoForgeVersion() {
        try {
            Class<?> loader = Class.forName("net.neoforged.fml.loading.FMLLoader");
            Object info;
            try { info = loader.getMethod("versionInfo").invoke(null); }
            catch (NoSuchMethodException newerLoader) {
                Object current = loader.getMethod("getCurrent").invoke(null);
                info = loader.getMethod("getVersionInfo").invoke(current);
            }
            return (String) info.getClass().getMethod("mcVersion").invoke(info);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("Cannot identify the active Minecraft version", exception);
        }
    }

    public static String implementation() {
        String game = current();
        try (var stream = VersionSelector.class.getResourceAsStream("/mcdr-variants.json")) {
            var variants = JsonParser.parseReader(new InputStreamReader(stream, StandardCharsets.UTF_8)).getAsJsonObject();
            if (!variants.has(game)) throw new IllegalStateException("Unsupported Minecraft version: " + game);
            return variants.get(game).getAsString();
        } catch (java.io.IOException exception) { throw new IllegalStateException(exception); }
    }
}
