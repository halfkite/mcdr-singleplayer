package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.util.List;
import org.junit.jupiter.api.Test;

/** The viewer shows both stores, so one store's failure must never hide the other. */
class BackupCatalogClientTest {
    private JsonObject row(String ref, String kind, boolean restorable, String reason) {
        var row = new JsonObject();
        row.addProperty("ref", ref);
        row.addProperty("kind", kind);
        row.addProperty("date", "2026-01-02 03:04");
        row.addProperty("comment", "comment");
        row.addProperty("operator", "Console");
        row.addProperty("size", 4096);
        row.addProperty("temporary", false);
        row.addProperty("restorable", restorable);
        row.addProperty("reason", reason);
        var dimensions = new JsonArray();
        dimensions.add("minecraft:overworld");
        row.add("dimensions", dimensions);
        return row;
    }

    private JsonObject catalog(JsonArray prime, String primeError, JsonArray chunk, String chunkError) {
        var value = new JsonObject();
        value.addProperty("world", "world");
        for (var entry : List.of(new String[] {"prime", primeError}, new String[] {"chunk", chunkError},
                new String[] {"vanilla", ""})) {
            var store = new JsonObject();
            store.add("backups", switch (entry[0]) {
                case "prime" -> prime;
                case "chunk" -> chunk;
                default -> new JsonArray();
            });
            store.addProperty("error", entry[1]);
            value.add(entry[0], store);
        }
        return value;
    }

    @Test void vanillaBackupsAreTheirOwnStoreAndRestorePath() {
        var value = new JsonObject();
        for (var key : List.of("prime", "chunk", "vanilla")) {
            var store = new JsonObject();
            var rows = new JsonArray();
            if (key.equals("vanilla")) {
                rows.add(row("vanilla:2026-10-11_15-11-53_w1.zip", "vanilla", true, ""));
            }
            store.add("backups", rows);
            store.addProperty("error", "");
            value.add(key, store);
        }
        var parsed = BackupCatalogClient.parse(value);
        assertEquals(1, parsed.vanilla().entries().size());
        var entry = parsed.vanilla().entries().get(0);
        assertTrue(entry.vanilla());
        assertFalse(entry.prime());
        // 界面按 ref 前缀选择离线命令，原版备份必须走 --vanilla-restore。
        assertTrue(entry.ref().startsWith("vanilla:"));
        assertTrue(parsed.prime().entries().isEmpty());
    }

    @Test void aMissingVanillaStoreIsAnEmptyStoreNotACrash() {
        var parsed = BackupCatalogClient.parse(catalog(new JsonArray(), "", new JsonArray(), ""));
        assertTrue(parsed.vanilla().entries().isEmpty());
        assertTrue(parsed.vanilla().error().isEmpty());
    }

    @Test void bothStoresAreParsedIndependently() {
        var prime = new JsonArray();
        prime.add(row("prime:7", "prime", true, ""));
        var chunk = new JsonArray();
        chunk.add(row("chunk:dynamic/slot1", "chunk", true, ""));
        chunk.add(row("chunk:dynamic/slot2", "chunk", false, "mcdr-singleplayer.catalog.partial_type"));

        var parsed = BackupCatalogClient.parse(catalog(prime, "", chunk, ""));
        assertEquals(1, parsed.prime().entries().size());
        assertEquals(2, parsed.chunk().entries().size());
        assertTrue(parsed.prime().entries().get(0).prime());
        assertFalse(parsed.chunk().entries().get(0).prime());
        assertEquals(List.of("minecraft:overworld"), parsed.chunk().entries().get(0).dimensions());
        // A partial chunk backup is listed but cannot be restored.
        assertFalse(parsed.chunk().entries().get(1).restorable());
        assertEquals("mcdr-singleplayer.catalog.partial_type", parsed.chunk().entries().get(1).reason());
        assertTrue(parsed.chunk().error().isEmpty());
    }

    @Test void aBrokenStoreKeepsItsReasonWithoutHidingTheOtherOne() {
        var chunk = new JsonArray();
        chunk.add(row("chunk:dynamic/slot1", "chunk", true, ""));
        var parsed = BackupCatalogClient.parse(catalog(new JsonArray(),
            "mcdr-singleplayer.catalog.missing_prime_backup", chunk, ""));

        assertEquals("mcdr-singleplayer.catalog.missing_prime_backup", parsed.prime().error());
        assertTrue(parsed.prime().entries().isEmpty());
        assertEquals(1, parsed.chunk().entries().size());
        assertTrue(parsed.chunk().error().isEmpty());
    }

    @Test void missingOrMalformedFieldsNeverBecomeAFabricatedRestorePoint() {
        var value = JsonParser.parseString("{\"prime\":{\"backups\":[{\"ref\":\"prime:1\"}]},"
            + "\"chunk\":{\"backups\":[{\"kind\":\"chunk\",\"date\":\"x\",\"ref\":\"chunk:overwrite\"}]}}")
            .getAsJsonObject();
        var parsed = BackupCatalogClient.parse(value);
        // Absent booleans default to "restorable", and absent lists stay empty.
        assertEquals(1, parsed.prime().entries().size());
        assertTrue(parsed.prime().entries().get(0).restorable());
        assertTrue(parsed.prime().entries().get(0).dimensions().isEmpty());
        assertEquals(0, parsed.prime().entries().get(0).size());
        // An unknown store is an empty store, never a crash.
        assertNotNull(BackupCatalogClient.parse(new JsonObject()).prime());
        assertTrue(BackupCatalogClient.parse(new JsonObject()).chunk().entries().isEmpty());
    }
}
