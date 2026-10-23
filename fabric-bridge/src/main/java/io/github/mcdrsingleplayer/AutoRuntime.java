package io.github.mcdrsingleplayer;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipInputStream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Disk discovery is token-free; installation and process I/O never run on the render thread. */
final class AutoRuntime {
    private static final Logger LOGGER = LoggerFactory.getLogger("mcdr_singleplayer_bridge");
    /** The tested MCDR release; the bundle's bootstrap.py declares the same version. */
    private static final String EXPECTED_MCDR = "2.16.0";
    /** Fallback for the materials folder when the mod container is unavailable; matches gradle.properties. */
    private static final String BRIDGE_VERSION = "0.6.2";
    private static final long SETUP_RECHECK_MILLIS = 3000;
    private final BridgeConfig config;
    private final Path gameConfig;
    private final Path stateFile;
    private final Path common;
    private final String bridgeVersion;
    private final String clientId = UUID.randomUUID().toString();
    private final CountDownLatch installRequested = new CountDownLatch(1);
    private final com.google.gson.JsonArray setupRequests = new com.google.gson.JsonArray();
    private McdrSetup setup;
    private volatile int bridgePort;
    private String world;
    private String session;
    private String hostPlayer;
    private String language;
    private volatile boolean closing;
    private volatile PythonStatus pythonStatus = PythonStatus.CHECKING;
    private volatile InstallProgress installProgress = new InstallProgress("preparing", 0);

    private enum PythonStatus { CHECKING, MISSING, READY }

    private record SetupCheck(boolean ready, String reason) { }

    AutoRuntime(BridgeConfig config, Path gameConfig, Path gameDirectory) {
        this(config, gameConfig, gameDirectory, BRIDGE_VERSION);
    }

    AutoRuntime(BridgeConfig config, Path gameConfig, Path gameDirectory, String bridgeVersion) {
        this.config = config;
        this.bridgePort = config.port;
        this.gameConfig = gameConfig.toAbsolutePath();
        this.bridgeVersion = stableVersion(bridgeVersion);
        this.stateFile = BridgeConfig.runtimeForGame(gameDirectory).resolve("clients").resolve(clientId).resolve("session.json");
        common = BridgeConfig.rootForGame(gameDirectory).toAbsolutePath().normalize();
        // Publish the initial "checking" state before the game can draw the menu.
        setup = new McdrSetup(stateFile.resolveSibling("setup-status.json"));
        setup.write();
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

    synchronized void publish(String world, String session, String hostPlayer, String language, int port) {
        bridgePort = port;
        publish(world, session, hostPlayer, language);
    }

    synchronized void closing() {
        closing = true;
        // The setup thread may be waiting for the user; a closing game never installs.
        installRequested.countDown();
        writeState(); // Keep the live world until SERVER_STOPPED confirms saving finished.
    }

    boolean pythonMissing() { return pythonStatus == PythonStatus.MISSING; }
    boolean pythonReady() { return pythonStatus == PythonStatus.READY; }
    boolean pythonChecking() { return pythonStatus == PythonStatus.CHECKING; }
    boolean autoInstallEnabled() { return config.autoInstall; }
    InstallProgress installProgress(boolean connected) {
        return connected ? new InstallProgress("ready", 0) : installProgress;
    }

    McdrSetup setupStatus() { return setup; }

    /** Installs MCDR after the user accepted the download from the main menu. */
    void requestInstall() {
        if (setup == null) return;
        setup.installing();
        setup.write();
        installRequested.countDown();
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
        data.addProperty("bridge_port", bridgePort);
        data.add("setup_requests", setupRequests.deepCopy());
        try {
            Files.createDirectories(stateFile.getParent());
            Path temporary = stateFile.resolveSibling(stateFile.getFileName() + ".tmp");
            Files.writeString(temporary, data.toString());
            Files.move(temporary, stateFile, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) { LOGGER.error("Could not publish MCDR client state ({})", e.getClass().getSimpleName()); }
    }

    void start() {
        setup.write();
        publish(null, null);
        Thread.ofVirtual().name("mcdr-python-detect").start(this::run);
    }

    /** Detect Python, then wait for the download decision before touching the shared MCDR directory. */
    private void run() {
        SetupCheck check;
        try {
            check = awaitSetupDecision();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
        if (check == null || closing) return;
        if (!check.ready()) {
            LOGGER.info("MCDR needs installation ({}); waiting for the main menu download", check.reason());
            try {
                installRequested.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (closing) return;
        }
        startController();
    }

    /**
     * Whether a configured interpreter is actually there; a bare command name is left to the
     * detector, which already resolved it before it reached the configuration.
     */
    private boolean pythonUsable(String python) {
        try {
            Path path = Path.of(python);
            return !path.isAbsolute() && !python.contains("/") && !python.contains("\\")
                    || Files.isRegularFile(path);
        } catch (RuntimeException e) {
            return false;
        }
    }

    /** Poll the installed runtime; Python has to exist before MCDR can be verified or installed. */
    private SetupCheck awaitSetupDecision() throws InterruptedException {
        while (!closing) {
            String python = config.pythonExecutable.isBlank() ? detectPython() : config.pythonExecutable;
            // A configured path that no longer exists is just as unusable as a missing interpreter,
            // and reporting it from the menu keeps the world from pausing over it later.
            if (python == null || !pythonUsable(python)) {
                pythonStatus = PythonStatus.MISSING;
                // A published reason is what makes the main menu offer help, so a missing Python is
                // reported there instead of waiting for the player to open a world.
                setup.check(McdrSetup.PYTHON_MISSING);
                setup.write();
                Thread.sleep(SETUP_RECHECK_MILLIS);
                continue;
            }
            pythonStatus = PythonStatus.READY;
            SetupCheck check = probe();
            setup.check(check.reason());
            setup.write();
            if (check.ready() || installRequested.await(SETUP_RECHECK_MILLIS, TimeUnit.MILLISECONDS)) return check;
        }
        return null;
    }

    /**
     * Report the setup state the menu needs: the published reason is either {@code ready} or the
     * concrete reason to download. A ready runtime must never also carry a download reason.
     */
    private SetupCheck probe() {
        Path runtimeRoot = common.resolve("runtime");
        Path environmentPython = runtimeRoot.resolve(".bridge-venv")
                .resolve(isWindows() ? "Scripts/python.exe" : "bin/python");
        if (!Files.isRegularFile(environmentPython)) return new SetupCheck(false, "missing");
        Path marker = runtimeRoot.resolve("runtime-install.json");
        String installed;
        try {
            installed = com.google.gson.JsonParser.parseString(Files.readString(marker))
                    .getAsJsonObject().get("mcdr").getAsString();
        } catch (IOException | RuntimeException e) {
            return new SetupCheck(false, "missing");
        }
        if (!EXPECTED_MCDR.equals(installed)) return new SetupCheck(false, "outdated");
        String reported = mcdrVersion(environmentPython);
        if (reported == null) return new SetupCheck(false, "broken");
        if (!EXPECTED_MCDR.equals(reported)) return new SetupCheck(false, "outdated");
        // The bundled plugin has to match this jar as well: upgrading the mod used to leave the old
        // plugin in place, which then never connected and looked like a runtime that refused to load.
        String plugin = pluginVersion(common.resolve("plugins/singleplayer_bridge.mcdr"));
        if (plugin == null) return new SetupCheck(false, "missing");
        if (!bridgeVersion.equals(plugin)) return new SetupCheck(false, "plugin");
        return new SetupCheck(true, McdrSetup.READY);
    }

    /** The version declared inside a packed MCDR plugin, or null when it cannot be read. */
    static String pluginVersion(Path plugin) {
        if (!Files.isRegularFile(plugin)) return null;
        try (java.util.zip.ZipFile archive = new java.util.zip.ZipFile(plugin.toFile())) {
            java.util.zip.ZipEntry entry = archive.getEntry("mcdreforged.plugin.json");
            if (entry == null) return null;
            String text = new String(archive.getInputStream(entry).readAllBytes(),
                    java.nio.charset.StandardCharsets.UTF_8);
            return com.google.gson.JsonParser.parseString(text).getAsJsonObject().get("version").getAsString();
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }

    /** Ask the isolated environment itself; a half-installed venv answers with a failure exit. */
    private String mcdrVersion(Path python) {
        try {
            Process process = new ProcessBuilder(python.toString(), "-c",
                    "import importlib.metadata as m; print(m.version('mcdreforged'))").redirectErrorStream(true).start();
            if (!process.waitFor(6, TimeUnit.SECONDS)) { process.destroyForcibly(); return null; }
            if (process.exitValue() != 0) return null;
            String output = new String(process.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).strip();
            return output.lines().reduce((first, last) -> last).orElse(output);
        } catch (IOException e) {
            return null;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        }
    }

    private void startController() {
        try {
            Files.createDirectories(common);
            Path resources = common.resolve("runtime/bootstrap-resources-" + bridgeVersion);
            extract(resources);
            String python = findPython();
            if (python == null) {
                pythonStatus = PythonStatus.MISSING;
                // Keep the menu honest: without an interpreter nothing can be installed.
                setup.check(McdrSetup.PYTHON_MISSING);
                setup.write();
                return;
            }
            pythonStatus = PythonStatus.READY;
            List<String> command;
            if (config.autoInstall) command = new ArrayList<>(List.of(python, resources.resolve("bridge_bootstrap.py").toString(),
                    "--resources", resources.toString(), "--common", common.toString(), "--expected-mcdr", EXPECTED_MCDR));
            else command = new ArrayList<>(List.of(python, common.resolve("runtime/bridge-runtime/bridge_supervisor.py").toString(), "--common", common.toString()));
            command.addAll(List.of("--config", gameConfig.toString(), "--state", stateFile.toString(),
                    "--client-id", clientId, "--parent-pid", Long.toString(ProcessHandle.current().pid())));
            Files.createDirectories(common.resolve("log"));
            LOGGER.info("MCDR controller starting; shared directory: {}. Installation progress: bootstrap.log", common);
            while (!closing) {
                Process process = new ProcessBuilder(command).redirectErrorStream(true)
                        .redirectOutput(ProcessBuilder.Redirect.appendTo(common.resolve("log/bootstrap.log").toFile())).start();
                if (!config.autoInstall) installProgress = new InstallProgress("starting", 0);
                Path progressFile = stateFile.resolveSibling("install-progress.json");
                while (!closing) {
                    try {
                        if (Files.isRegularFile(progressFile) && Files.size(progressFile) <= 4096) {
                            InstallProgress value = InstallProgress.parse(Files.readString(progressFile), clientId);
                            if (value != null) installProgress = value;
                        }
                    } catch (IOException ignored) { /* Retain the last stage during atomic replacement. */ }
                    if (process.waitFor(500, TimeUnit.MILLISECONDS)) {
                        if (!closing) installProgress = new InstallProgress(process.exitValue() == 2 ? "waiting_instance" : "failed", 0);
                        break;
                    }
                }
                if (closing || process.exitValue() != 2) break;
                Thread.sleep(1000);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (Exception e) {
            installProgress = new InstallProgress("failed", 0);
            LOGGER.error("Automatic MCDR installation failed ({})", e.getMessage());
        }
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
                    Path temporary = Files.createTempFile(target.getParent(), "mcdr-resource-", ".tmp");
                    try {
                        Files.copy(zip, temporary, StandardCopyOption.REPLACE_EXISTING);
                        Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
                    } finally { Files.deleteIfExists(temporary); }
                }
            }
        }
    }

    private static boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("windows");
    }

    /**
     * Development builds share the stable materials folder of the release they belong to, so a
     * locally built jar reuses the materials a published build already extracted.
     */
    private static String stableVersion(String version) {
        int development = version.indexOf("-dev.");
        return development > 0 ? version.substring(0, development) : version;
    }

    /** Repeating the full search keeps a later Python installation from requiring a game restart. */
    private String detectPython() {
        String python = findPython();
        if (python == null && pythonStatus != PythonStatus.MISSING) {
            LOGGER.info("Python 3.10 or newer with pip was not found; waiting for installation");
        }
        return python;
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
