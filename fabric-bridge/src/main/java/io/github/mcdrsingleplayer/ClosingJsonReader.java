package io.github.mcdrsingleplayer;

import com.google.gson.Gson;
import java.io.IOException;
import java.io.Reader;

/** Release optional mod configuration handles even if Gson rejects their contents. */
public final class ClosingJsonReader {
    private ClosingJsonReader() {}

    public static <T> T read(Gson gson, Reader reader, Class<T> type) throws IOException {
        try (reader) { return gson.fromJson(reader, type); }
    }
}
