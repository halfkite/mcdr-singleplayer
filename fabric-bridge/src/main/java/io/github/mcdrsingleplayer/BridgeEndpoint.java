package io.github.mcdrsingleplayer;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/** Loopback transport. Game event callbacks only enqueue; socket writes run off-thread. */
final class BridgeEndpoint implements AutoCloseable {
    static final int MAX_FRAME = 65536;
    static final String SAVE_AND_QUIT = "__bridge_save_and_quit__";
    private final String token;
    private final String gameVersion;
    private final String worldPath;
    private final Consumer<Request> commands;
    private final ServerSocket listener;
    private final ScheduledExecutorService heartbeat;
    private final Semaphore handshakes = new Semaphore(4);
    private final Object eventLock = new Object();
    private final Set<String> players = new HashSet<>();
    final String session = UUID.randomUUID().toString();
    volatile boolean paused;
    volatile String hostPlayer;
    volatile String language = "en_us";
    volatile String progressPath;
    volatile JsonObject commandTree;
    private String treeRevision;
    private String[] treeChunks;
    private volatile boolean closed;
    private Peer active;
    private final Map<String, CompletableFuture<List<String>>> completions = new ConcurrentHashMap<>();

    boolean clientChat(String player, String command) {
        synchronized (eventLock) {
            if (closed || active == null || active.dead.get() || !players.contains(player) || command.length() > 16384) return false;
            JsonObject event = event("chat");
            event.addProperty("player", player);
            event.addProperty("text", command);
            active.offer(event);
            return true;
        }
    }

    CompletableFuture<List<String>> suggest(String player, String command) {
        synchronized (eventLock) {
            if (closed || active == null || active.dead.get() || !players.contains(player)
                    || command.length() > 2048 || completions.size() >= 16) return CompletableFuture.completedFuture(List.of());
            String id = UUID.randomUUID().toString();
            CompletableFuture<List<String>> future = new CompletableFuture<>();
            completions.put(id, future);
            future.completeOnTimeout(List.of(), 2, TimeUnit.SECONDS).whenComplete((value, error) -> completions.remove(id));
            JsonObject event = event("suggest_request");
            event.addProperty("id", id);
            event.addProperty("player", player);
            event.addProperty("text", command);
            active.offer(event);
            return future;
        }
    }

    BridgeEndpoint(int port, String token, String gameVersion, String worldPath, Consumer<Request> commands) throws IOException {
        this.token = token;
        this.gameVersion = gameVersion;
        this.worldPath = worldPath;
        this.commands = commands;
        listener = new ServerSocket();
        listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port));
        heartbeat = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "mcdr-bridge-heartbeat");
            t.setDaemon(true);
            return t;
        });
        heartbeat.scheduleAtFixedRate(() -> {
            JsonObject event = event("heartbeat");
            event.addProperty("paused", paused);
            publish(event);
        }, 2, 2, TimeUnit.SECONDS);
        Thread.ofVirtual().name("mcdr-bridge-accept").start(this::acceptLoop);
    }

    int port() { return listener.getLocalPort(); }

    boolean connected() {
        synchronized (eventLock) { return active != null && !active.dead.get(); }
    }

    JsonObject event(String type) {
        JsonObject event = new JsonObject();
        event.addProperty("type", type);
        event.addProperty("session", session);
        return event;
    }

    void publish(JsonObject event) {
        synchronized (eventLock) {
            if (active != null) active.offer(event);
        }
    }

    void playerJoined(String name) {
        synchronized (eventLock) {
            if (!players.add(name)) return;
            JsonObject event = event("player_joined");
            event.addProperty("player", name);
            if (active != null) active.offer(event);
        }
    }

    void playerLeft(String name) {
        synchronized (eventLock) {
            if (!players.remove(name)) return;
            JsonObject event = event("player_left");
            event.addProperty("player", name);
            if (active != null) active.offer(event);
        }
    }

    void pause(boolean value) {
        if (paused == value) return;
        paused = value;
        JsonObject event = event("pause");
        event.addProperty("paused", value);
        publish(event);
    }

    private JsonObject ready() {
        JsonObject event = event("ready");
        event.addProperty("protocol", 1);
        event.addProperty("game_version", gameVersion);
        event.addProperty("world_path", worldPath);
        event.addProperty("paused", paused);
        if (hostPlayer != null) event.addProperty("host_player", hostPlayer);
        event.addProperty("language", language);
        if (progressPath != null) event.addProperty("progress_path", progressPath);
        JsonArray snapshot = new JsonArray();
        players.stream().sorted().forEach(snapshot::add);
        event.add("players", snapshot);
        return event;
    }

    private void acceptLoop() {
        while (!closed) {
            try {
                Socket socket = listener.accept();
                if (!handshakes.tryAcquire()) {
                    socket.close();
                    continue;
                }
                Thread.ofVirtual().name("mcdr-bridge-peer").start(() -> handle(socket));
            } catch (IOException ignored) {
                if (!closed) close();
            }
        }
    }

    private void handle(Socket socket) {
        Peer peer = new Peer(socket);
        try (socket) {
            socket.setSoTimeout(5000);
            JsonObject hello = readFrame(socket.getInputStream());
            if (!"hello".equals(text(hello, "type", 32)) || integer(hello, "protocol") != 1
                    || !MessageDigest.isEqual(token.getBytes(StandardCharsets.UTF_8),
                    text(hello, "token", 256).getBytes(StandardCharsets.UTF_8))) return;
            synchronized (eventLock) {
                if (closed || active != null && !active.dead.get()) return;
                active = peer;
                peer.offer(ready());
            }
            socket.setSoTimeout(0);
            Thread.ofVirtual().name("mcdr-bridge-output").start(peer::writeLoop);
            while (!closed && !peer.dead.get()) {
                JsonObject record = readFrame(socket.getInputStream());
                if ("command_tree".equals(text(record, "type", 32))) {
                    if (!session.equals(text(record, "session", 128))) throw new IOException("Stale command tree");
                    String revision = text(record, "revision", 128);
                    int total = (int) integer(record, "total");
                    int index = (int) integer(record, "index");
                    String payload = text(record, "payload", 6000);
                    if (total < 1 || total > 256 || index < 0 || index >= total) throw new IOException("Invalid command tree chunk");
                    if (!revision.equals(treeRevision)) {
                        treeRevision = revision;
                        treeChunks = new String[total];
                    }
                    if (treeChunks.length != total) throw new IOException("Invalid command tree size");
                    treeChunks[index] = payload;
                    if (java.util.Arrays.stream(treeChunks).allMatch(java.util.Objects::nonNull)) {
                        var tree = JsonParser.parseString(String.join("", treeChunks));
                        if (!tree.isJsonObject()) throw new IOException("Invalid command tree");
                        commandTree = tree.getAsJsonObject();
                        treeChunks = new String[total];
                    }
                    continue;
                }
                if ("suggest_result".equals(text(record, "type", 32))) {
                    if (!session.equals(text(record, "session", 128))) throw new IOException("Stale completion session");
                    String id = text(record, "id", 128);
                    var values = record.getAsJsonArray("suggestions");
                    if (values == null || values.size() > 100) throw new IOException("Invalid suggestions");
                    java.util.ArrayList<String> result = new java.util.ArrayList<>();
                    for (var value : values) {
                        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString() || value.getAsString().length() > 2048)
                            throw new IOException("Invalid suggestion");
                        result.add(value.getAsString());
                    }
                    var future = completions.remove(id);
                    if (future != null) future.complete(result);
                    continue;
                }
                if (!"command".equals(text(record, "type", 32))) throw new IOException("Unexpected request");
                String requestSession = text(record, "session", 128);
                String id = text(record, "id", 128);
                String command = text(record, "command", 16384);
                long deadline = integer(record, "deadline");
                Request request = new Request(peer, id, command, deadline);
                if (!session.equals(requestSession)) {
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_rejected_stale_world_session").getString());
                } else if (deadline < System.currentTimeMillis() || deadline > System.currentTimeMillis() + 15000) {
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_rejected_expired_or_invalid_deadline").getString());
                } else if (paused && !SAVE_AND_QUIT.equals(command)) {
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_rejected_world_paused").getString());
                } else if (peer.pending.incrementAndGet() > 64) {
                    peer.pending.decrementAndGet();
                    request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_rejected_queue_full").getString());
                } else {
                    request.counted = true;
                    try {
                        commands.accept(request);
                    } catch (RuntimeException e) {
                        request.complete(false, net.minecraft.network.chat.Component.translatable("mcdr-singleplayer.error.command_could_not_be_scheduled").getString());
                    }
                }
            }
        } catch (Exception ignored) {
            // Never include token-bearing input in logs. Invalid frames terminate the connection.
        } finally {
            peer.close();
            synchronized (eventLock) {
                if (active == peer) {
                    active = null;
                    commandTree = null;
                    treeRevision = null;
                    treeChunks = null;
                }
            }
            handshakes.release();
        }
    }

    static String text(JsonObject record, String key, int limit) throws IOException {
        var value = record.get(key);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) {
            throw new IOException("Invalid string field");
        }
        String text = value.getAsString();
        if (text.length() > limit || text.indexOf('\0') >= 0) throw new IOException("Invalid string field");
        return text;
    }

    private static long integer(JsonObject record, String key) throws IOException {
        var value = record.get(key);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()
                || !value.getAsString().matches("-?[0-9]{1,18}")) throw new IOException("Invalid integer field");
        return value.getAsLong();
    }

    static JsonObject readFrame(InputStream stream) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        for (int n = 0; n < MAX_FRAME; n++) {
            int next = stream.read();
            if (next < 0) throw new IOException("Connection ended");
            if (next == '\n') {
                try {
                    String raw = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(bytes.toByteArray())).toString();
                    var json = JsonParser.parseString(raw);
                    if (!json.isJsonObject()) throw new IOException("Invalid frame");
                    return json.getAsJsonObject();
                } catch (CharacterCodingException | RuntimeException e) {
                    throw new IOException("Invalid frame");
                }
            }
            bytes.write(next);
        }
        throw new IOException("Frame exceeds limit");
    }

    final class Request {
        private final Peer peer;
        final String id;
        final String command;
        final long deadline;
        private final AtomicBoolean completed = new AtomicBoolean();
        boolean counted;

        Request(Peer peer, String id, String command, long deadline) {
            this.peer = peer;
            this.id = id;
            this.command = command;
            this.deadline = deadline;
        }

        boolean valid() {
            return !closed && !peer.dead.get() && (!paused || SAVE_AND_QUIT.equals(command)) && deadline >= System.currentTimeMillis();
        }

        void complete(boolean success, String message) {
            if (!completed.compareAndSet(false, true)) return;
            if (counted) peer.pending.decrementAndGet();
            JsonObject result = event("command_result");
            result.addProperty("id", id);
            result.addProperty("success", success);
            result.addProperty("text", message.length() > 8000 ? message.substring(0, 8000) + "…" : message);
            peer.offer(result);
        }
    }

    private final class Peer {
        final Socket socket;
        final ArrayBlockingQueue<JsonObject> output = new ArrayBlockingQueue<>(256);
        final AtomicBoolean dead = new AtomicBoolean();
        final AtomicInteger pending = new AtomicInteger();

        Peer(Socket socket) { this.socket = socket; }

        void offer(JsonObject event) {
            if (!dead.get() && !output.offer(event)) close();
        }

        void writeLoop() {
            try {
                var stream = socket.getOutputStream();
                while (!dead.get()) {
                    JsonObject event = output.poll(1, TimeUnit.SECONDS);
                    if (event == null) continue;
                    byte[] frame = (event.toString() + "\n").getBytes(StandardCharsets.UTF_8);
                    if (frame.length > MAX_FRAME) throw new IOException("Frame exceeds limit");
                    stream.write(frame);
                    stream.flush();
                    if ("world_stopped".equals(event.get("type").getAsString())) {
                        close();
                        return;
                    }
                }
            } catch (IOException | InterruptedException ignored) {
                close();
            }
        }

        void close() {
            if (dead.compareAndSet(false, true)) {
                try { socket.close(); } catch (IOException ignored) { }
            }
        }
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        completions.values().forEach(future -> future.complete(List.of()));
        heartbeat.shutdownNow();
        try { listener.close(); } catch (IOException ignored) { }
        synchronized (eventLock) {
            if (active != null) {
                active.offer(event("world_stopped"));
                Peer peer = active;
                // Give the writer a bounded chance to deliver the final event off the game thread.
                Thread.ofVirtual().start(() -> {
                    try { Thread.sleep(500); } catch (InterruptedException ignored) { }
                    peer.close();
                });
            }
        }
    }
}
