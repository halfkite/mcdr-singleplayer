package io.github.mcdrsingleplayer;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipInputStream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Disk discovery is token-free; installation and process I/O never run on the render thread. */
final class AutoRuntime {
    private static final Logger LOGGER = LoggerFactory.getLogger("mcdr_singleplayer_bridge");
    private final BridgeConfig config;
    private final Path gameConfig;
    private final Path stateFile;
    private final Path common;
    private final String clientId = UUID.randomUUID().toString();
    private String world;
    private String session;
    private String hostPlayer;
    private String language;
    private boolean closing;
    private final com.google.gson.JsonArray setupRequests = new com.google.gson.JsonArray();

    AutoRuntime(BridgeConfig config, Path gameConfig, Path gameDirectory) {
        this.config = config;
        this.gameConfig = gameConfig.toAbsolutePath();
        this.stateFile = BridgeConfig.runtimeForGame(gameDirectory).resolve(".mcdr_bridge_session.json");
        common = BridgeConfig.rootForGame(gameDirectory).toAbsolutePath().normalize();
    }

    synchronized void publish(String world, String session) {
        this.world = world;
        this.session = session;
        writeState();
    }

    synchronized void publish(String world, String session, String hostPlayer, String language) {
        this.hostPlayer = hostPlayer;
        this.language = language;
        publish(world, session);
    }

    synchronized void closing() {
        closing = true;
        writeState(); // Keep the live world until SERVER_STOPPED confirms saving finished.
    }

    synchronized void requestSetup(String action, String player) {
        JsonObject request = new JsonObject();
        request.addProperty("id", UUID.randomUUID().toString());
        request.addProperty("session", session);
        request.addProperty("action", action);
        request.addProperty("player", player);
        if (setupRequests.size() >= 64) setupRequests.remove(0);
        setupRequests.add(request);
        writeState();
    }

    private void writeState() {
        JsonObject data = new JsonObject();
        data.addProperty("client_id", clientId);
        data.addProperty("client_pid", ProcessHandle.current().pid());
        data.addProperty("closing", closing);
        data.addProperty("world_path", world);
        data.addProperty("session", session);
        data.addProperty("host_player", hostPlayer);
        data.addProperty("language", language);
        data.add("setup_requests", setupRequests.deepCopy());
        try {
            Files.createDirectories(stateFile.getParent());
            Path temporary = stateFile.resolveSibling(stateFile.getFileName() + ".tmp");
            Files.writeString(temporary, data.toString());
            Files.move(temporary, stateFile, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) { LOGGER.error("Could not publish MCDR client state ({})", e.getClass().getSimpleName()); }
    }

    void start() {
        publish(null, null);
        Thread.ofVirtual().name("mcdr-auto-install").start(() -> {
            try {
                Files.createDirectories(common);
                Path resources = common.resolve("runtime/bootstrap-resources-0.3.10");
                extract(resources);
                String python = python();
                List<String> command;
                if (config.autoInstall) command = new ArrayList<>(List.of(python, resources.resolve("bridge_bootstrap.py").toString(),
                        "--resources", resources.toString(), "--common", common.toString()));
                else command = new ArrayList<>(List.of(python, common.resolve("runtime/bridge-runtime/bridge_supervisor.py").toString(), "--common", common.toString()));
                command.addAll(List.of("--config", gameConfig.toString(), "--state", stateFile.toString(),
                        "--client-id", clientId, "--parent-pid", Long.toString(ProcessHandle.current().pid())));
                Files.createDirectories(common.resolve("log"));
                new ProcessBuilder(command).redirectErrorStream(true)
                        .redirectOutput(ProcessBuilder.Redirect.appendTo(common.resolve("log/bootstrap.log").toFile())).start();
                LOGGER.info("MCDR controller starting; shared directory: {}. Installation progress: bootstrap.log", common);
            } catch (Exception e) { LOGGER.error("Automatic MCDR installation failed ({})", e.getMessage()); }
        });
    }

    private void extract(Path destination) throws IOException {
        Files.createDirectories(destination);
        try (var stream = AutoRuntime.class.getResourceAsStream("/mcdr-install.zip")) {
            if (stream == null) throw new IOException("Missing bundled installer resources");
            try (var zip = new ZipInputStream(stream)) {
                java.util.zip.ZipEntry entry;
                while ((entry = zip.getNextEntry()) != null) {
                    Path target = destination.resolve(entry.getName()).normalize();
                    if (!target.startsWith(destination) || entry.isDirectory()) continue;
                    Files.createDirectories(target.getParent());
                    Files.copy(zip, target, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
    }

    private String python() throws Exception {
        List<List<String>> candidates = new ArrayList<>();
        if (!config.pythonExecutable.isBlank()) candidates.add(List.of(config.pythonExecutable));
        Path owned = common.resolve("runtime/python-runtime/python.exe");
        if (Files.exists(owned)) candidates.add(List.of(owned.toString()));
        candidates.add(List.of("py", "-3"));
        candidates.add(List.of("python3"));
        candidates.add(List.of("python"));
        for (var candidate : candidates) {
            List<String> command = new ArrayList<>(candidate);
            command.addAll(List.of("-c", "import sys; assert sys.version_info >= (3, 10); print(sys.executable)"));
            try {
                Process check = new ProcessBuilder(command).redirectErrorStream(true).start();
                if (!check.waitFor(10, TimeUnit.SECONDS)) { check.destroyForcibly(); continue; }
                if (check.exitValue() == 0) return new String(check.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).strip();
            } catch (IOException ignored) { }
        }
        if (!config.autoInstall || !System.getProperty("os.name").toLowerCase(Locale.ROOT).contains("windows")
                || !System.getProperty("os.arch").equals("amd64")) throw new IOException("Python >= 3.10 required; configure pythonExecutable");
        Path installer = common.resolve("runtime/python-3.14.5-amd64.exe");
        String hash = "f9c09f5ed6f796fd1a8bc5ddfa41715a494b453c4781f0e35d5077cf9fa58f6d";
        HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(15)).followRedirects(HttpClient.Redirect.NORMAL).build();
        boolean downloaded = false;
        for (String base : List.of("https://www.python.org/ftp/python/", "https://repo.huaweicloud.com/python/")) {
            try {
                var request = HttpRequest.newBuilder(URI.create(base + "3.14.5/python-3.14.5-amd64.exe")).timeout(Duration.ofSeconds(90)).GET().build();
                var response = http.send(request, HttpResponse.BodyHandlers.ofByteArray());
                if (response.statusCode() != 200 || !HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(response.body())).equals(hash))
                    throw new IOException("Python installer download/hash failed");
                Files.write(installer, response.body());
                downloaded = true;
                break;
            } catch (Exception e) { LOGGER.warn("Python download failed; trying next source ({})", e.getClass().getSimpleName()); }
        }
        if (!downloaded) throw new IOException("All Python download sources failed");
        Process setup = new ProcessBuilder(installer.toString(), "/quiet", "InstallAllUsers=0", "TargetDir=" + owned.getParent(),
                "Include_launcher=0", "InstallLauncherAllUsers=0", "PrependPath=0", "Include_test=0")
                .redirectErrorStream(true).redirectOutput(common.resolve("log/python-install.log").toFile()).start();
        if (!setup.waitFor(5, TimeUnit.MINUTES) || setup.exitValue() != 0 || !Files.exists(owned))
            throw new IOException("Python installation failed; see log/python-install.log");
        return owned.toString();
    }
}
