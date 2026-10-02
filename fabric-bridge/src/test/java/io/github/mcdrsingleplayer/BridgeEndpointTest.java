package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;
import com.google.gson.JsonObject;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class BridgeEndpointTest {
    @Test void commandGraphsReplaceAtomicallyAndCannotCrossWorldSessions() throws Exception {
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/world", request -> {})) {
            endpoint.hostPlayer = "Main";
            endpoint.language = "zh_cn";
            try (var socket = connect(endpoint, TOKEN)) {
                var ready = BridgeEndpoint.readFrame(socket.getInputStream());
                assertEquals("Main", ready.get("host_player").getAsString());
                assertEquals("zh_cn", ready.get("language").getAsString());
                String graph = "{\"roots\":[0],\"nodes\":[{\"name\":\"!!custom\",\"kind\":\"literal\",\"children\":[],\"redirect\":null}]}";
                for (int index : new int[]{1, 0}) {
                    var chunk = endpoint.event("command_tree");
                    chunk.addProperty("revision", "first");
                    chunk.addProperty("index", index);
                    chunk.addProperty("total", 2);
                    chunk.addProperty("payload", index == 0 ? graph.substring(0, 40) : graph.substring(40));
                    write(socket, chunk);
                    if (index == 1) assertNull(endpoint.commandTree);
                }
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
                while (endpoint.commandTree == null && System.nanoTime() < deadline) Thread.sleep(5);
                assertNotNull(endpoint.commandTree);
                assertEquals("!!custom", endpoint.commandTree.getAsJsonArray("nodes").get(0).getAsJsonObject().get("name").getAsString());
                var stale = endpoint.event("command_tree");
                stale.addProperty("session", "other-world");
                stale.addProperty("revision", "stale");
                stale.addProperty("total", 1);
                stale.addProperty("index", 0);
                stale.addProperty("payload", graph);
                write(socket, stale);
                assertEquals(-1, socket.getInputStream().read());
            }
        }
    }
    @Test void clientCommandsAndNativeSuggestionsUseTheCurrentAuthenticatedPeer() throws Exception {
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/world", request -> {})) {
            endpoint.playerJoined("Steve");
            assertFalse(endpoint.clientChat("Steve", "!!MCDR"));
            try (var socket = connect(endpoint, TOKEN)) {
                BridgeEndpoint.readFrame(socket.getInputStream());
                assertFalse(endpoint.clientChat("Unknown", "!!MCDR"));
                assertTrue(endpoint.clientChat("Steve", "!!MCDR status"));
                var chat = BridgeEndpoint.readFrame(socket.getInputStream());
                assertEquals("chat", chat.get("type").getAsString());
                var future = endpoint.suggest("Steve", "!!MCDR plugin re");
                var event = BridgeEndpoint.readFrame(socket.getInputStream());
                var result = endpoint.event("suggest_result");
                result.add("id", event.get("id"));
                var values = new com.google.gson.JsonArray();
                values.add("!!MCDR plugin reload");
                result.add("suggestions", values);
                write(socket, result);
                assertEquals(java.util.List.of("!!MCDR plugin reload"), future.get(3, TimeUnit.SECONDS));
            }
        }
    }
    private static final String TOKEN = "a".repeat(64);

    private static void write(Socket socket, JsonObject record) throws IOException {
        socket.getOutputStream().write((record + "\n").getBytes(StandardCharsets.UTF_8));
        socket.getOutputStream().flush();
    }

    private static Socket connect(BridgeEndpoint endpoint, String token) throws IOException {
        Socket socket = new Socket("127.0.0.1", endpoint.port());
        socket.setSoTimeout(3000);
        JsonObject hello = new JsonObject();
        hello.addProperty("type", "hello");
        hello.addProperty("protocol", 1);
        hello.addProperty("token", token);
        write(socket, hello);
        return socket;
    }

    private static JsonObject command(BridgeEndpoint endpoint, String session, long deadline) {
        JsonObject request = endpoint.event("command");
        request.addProperty("session", session);
        request.addProperty("id", "request-1");
        request.addProperty("command", "say 测试");
        request.addProperty("deadline", deadline);
        return request;
    }

    @Test void rejectsAuthenticationWithoutRunningCommands() throws Exception {
        var requests = new LinkedBlockingQueue<BridgeEndpoint.Request>();
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/world", requests::add);
             var socket = connect(endpoint, "b".repeat(64))) {
            assertEquals(-1, socket.getInputStream().read());
            assertTrue(requests.isEmpty());
        }
    }

    @Test void snapshotAndPlayerChangesHaveExactlyOneEvent() throws Exception {
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/世界", request -> {})) {
            endpoint.playerJoined("Steve");
            try (var socket = connect(endpoint, TOKEN)) {
                var ready = BridgeEndpoint.readFrame(socket.getInputStream());
                assertEquals("ready", ready.get("type").getAsString());
                assertEquals("Steve", ready.getAsJsonArray("players").get(0).getAsString());
                endpoint.playerJoined("Steve");
                endpoint.playerJoined("Alex");
                var joined = BridgeEndpoint.readFrame(socket.getInputStream());
                assertEquals("Alex", joined.get("player").getAsString());
                endpoint.playerLeft("Steve");
                assertEquals("player_left", BridgeEndpoint.readFrame(socket.getInputStream()).get("type").getAsString());
            }
        }
    }

    @Test void staleExpiredAndPausedRequestsNeverReachGameExecutor() throws Exception {
        var requests = new LinkedBlockingQueue<BridgeEndpoint.Request>();
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/world", requests::add);
             var socket = connect(endpoint, TOKEN)) {
            BridgeEndpoint.readFrame(socket.getInputStream());
            write(socket, command(endpoint, "old-world", System.currentTimeMillis() + 10000));
            assertFalse(BridgeEndpoint.readFrame(socket.getInputStream()).get("success").getAsBoolean());
            write(socket, command(endpoint, endpoint.session, System.currentTimeMillis() - 1));
            assertFalse(BridgeEndpoint.readFrame(socket.getInputStream()).get("success").getAsBoolean());
            endpoint.pause(true);
            assertEquals("pause", BridgeEndpoint.readFrame(socket.getInputStream()).get("type").getAsString());
            write(socket, command(endpoint, endpoint.session, System.currentTimeMillis() + 10000));
            assertFalse(BridgeEndpoint.readFrame(socket.getInputStream()).get("success").getAsBoolean());
            assertTrue(requests.isEmpty());
        }
    }

    @Test void commandCompletesOnceAndDisconnectedRequestBecomesInvalid() throws Exception {
        var requests = new LinkedBlockingQueue<BridgeEndpoint.Request>();
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/world", requests::add);
             var socket = connect(endpoint, TOKEN)) {
            BridgeEndpoint.readFrame(socket.getInputStream());
            write(socket, command(endpoint, endpoint.session, System.currentTimeMillis() + 10000));
            var request = requests.poll(3, TimeUnit.SECONDS);
            assertNotNull(request);
            assertTrue(request.valid());
            request.complete(true, "世界 ✓");
            request.complete(false, "must not be delivered");
            var result = BridgeEndpoint.readFrame(socket.getInputStream());
            assertEquals("世界 ✓", result.get("text").getAsString());
            endpoint.close();
            assertFalse(request.valid());
            assertEquals("world_stopped", BridgeEndpoint.readFrame(socket.getInputStream()).get("type").getAsString());
        }
    }

    @Test void rejectsOversizedAndInvalidUtf8Frames() {
        assertThrows(IOException.class, () -> BridgeEndpoint.readFrame(new ByteArrayInputStream(new byte[65536])));
        assertThrows(IOException.class, () -> BridgeEndpoint.readFrame(new ByteArrayInputStream(new byte[]{(byte) 0xff, '\n'})));
        assertThrows(IOException.class, () -> BridgeEndpoint.readFrame(new ByteArrayInputStream("[]\n".getBytes(StandardCharsets.UTF_8))));
    }

    @Test void saveAndQuitCanReachClientWhilePausedButCannotCrossSessions() throws Exception {
        var requests = new LinkedBlockingQueue<BridgeEndpoint.Request>();
        try (var endpoint = new BridgeEndpoint(0, TOKEN, "26.3", "D:/world", requests::add);
             var socket = connect(endpoint, TOKEN)) {
            BridgeEndpoint.readFrame(socket.getInputStream());
            endpoint.pause(true);
            BridgeEndpoint.readFrame(socket.getInputStream());
            var stale = command(endpoint, "old-world", System.currentTimeMillis() + 10000);
            stale.addProperty("command", BridgeEndpoint.SAVE_AND_QUIT);
            write(socket, stale);
            assertFalse(BridgeEndpoint.readFrame(socket.getInputStream()).get("success").getAsBoolean());
            assertTrue(requests.isEmpty());
            var valid = command(endpoint, endpoint.session, System.currentTimeMillis() + 10000);
            valid.addProperty("command", BridgeEndpoint.SAVE_AND_QUIT);
            write(socket, valid);
            var request = requests.poll(3, TimeUnit.SECONDS);
            assertNotNull(request);
            assertTrue(request.valid());
        }
    }
}
