package io.github.mcdrsingleplayer;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonSyntaxException;
import java.io.IOException;
import java.io.StringReader;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ClosingJsonReaderTest {
    static final class TrackedReader extends StringReader {
        boolean closed;
        TrackedReader(String value) { super(value); }
        @Override public void close() { closed = true; super.close(); }
    }

    @Test void preservesConfigurationAndClosesReader() throws IOException {
        var reader = new TrackedReader("{\"quota\":42}");
        assertEquals(42, ClosingJsonReader.read(new Gson(), reader, JsonObject.class).get("quota").getAsInt());
        assertTrue(reader.closed);
    }

    @Test void malformedConfigurationStillClosesReader() {
        var reader = new TrackedReader("{\"quota\":");
        assertThrows(JsonSyntaxException.class, () -> ClosingJsonReader.read(new Gson(), reader, JsonObject.class));
        assertTrue(reader.closed);
    }
}
