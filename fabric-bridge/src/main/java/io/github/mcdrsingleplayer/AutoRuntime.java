package io.github.mcdrsingleplayer;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.*;
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
    private volatile boolean closing;
    private volatile PythonStatus pythonStatus = PythonStatus.CHECKING;
    private final com.google.gson.JsonArray setupRequests = new com.google.gson.JsonArray();

    private enum PythonStatus { CHECKING, MISSING, READY }

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

    boolean pythonMissing() { return pythonStatus == PythonStatus.MISSING; }

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
        Thread.ofVirtual().name("mcdr-python-detect").start(() -> {
            String python = null;
            while (!closing && python == null) {
                python = findPython();
                if (python == null) {
                    if (pythonStatus != PythonStatus.MISSING) {
                        LOGGER.info("Python 3.10 or newer with pip was not found; waiting for installation in a singleplayer world");
                    }
                    pythonStatus = PythonStatus.MISSING;
                    try { Thread.sleep(3000); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
                }
            }
            if (closing || python == null) return;
            pythonStatus = PythonStatus.READY;
            try {
                Files.createDirectories(common);
                Path resources = common.resolve("runtime/bootstrap-resources-0.3.10");
                extract(resources);
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

    private String findPython() {
        List<List<String>> candidates = new ArrayList<>();
        if (!config.pythonExecutable.isBlank()) candidates.add(List.of(config.pythonExecutable));
        Path owned = common.resolve("runtime/python-runtime/python.exe");
        if (Files.isRegularFile(owned)) candidates.add(List.of(owned.toString()));
        addWindowsInstallations(candidates);
        candidates.add(List.of("py", "-3"));
        candidates.add(List.of("python3"));
        candidates.add(List.of("python"));
        for (var candidate : candidates) {
            List<String> command = new ArrayList<>(candidate);
            command.addAll(List.of("-c", "import sys, pip; assert sys.version_info >= (3, 10); print(sys.executable)"));
            try {
                Process check = new ProcessBuilder(command).redirectErrorStream(true).start();
                if (!check.waitFor(4, TimeUnit.SECONDS)) { check.destroyForcibly(); continue; }
                if (check.exitValue() == 0) {
                    String output = new String(check.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).strip();
                    if (!output.isBlank()) return output.lines().reduce((first, last) -> last).orElse(output);
                }
            } catch (IOException ignored) { }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); return null; }
        }
        return null;
    }

    private static void addWindowsInstallations(List<List<String>> candidates) {
        if (!System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("windows")) return;
        String local = System.getenv("LOCALAPPDATA");
        if (local != null) {
            Path launcher = Path.of(local, "Programs", "Python", "Launcher", "py.exe");
            if (Files.isRegularFile(launcher)) candidates.add(List.of(launcher.toString(), "-3"));
            addInstalledPythonDirectories(candidates, Path.of(local, "Programs", "Python"));
        }
        addInstalledPythonDirectories(candidates, Path.of(System.getenv().getOrDefault("ProgramFiles", "C:\\Program Files")));
        String programFilesX86 = System.getenv("ProgramFiles(x86)");
        if (programFilesX86 != null) addInstalledPythonDirectories(candidates, Path.of(programFilesX86));
        String windows = System.getenv("WINDIR");
        if (windows != null) {
            Path launcher = Path.of(windows, "py.exe");
            if (Files.isRegularFile(launcher)) candidates.add(List.of(launcher.toString(), "-3"));
        }
    }

    private static void addInstalledPythonDirectories(List<List<String>> candidates, Path directory) {
        if (!Files.isDirectory(directory)) return;
        try (var entries = Files.list(directory)) {
            entries.filter(Files::isDirectory).filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).startsWith("python"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString(), Comparator.reverseOrder()))
                    .map(path -> path.resolve("python.exe")).filter(Files::isRegularFile)
                    .forEach(path -> candidates.add(List.of(path.toString())));
        } catch (IOException ignored) { }
    }
}
