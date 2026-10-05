package io.github.mcdrsingleplayer;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.HexFormat;

final class BridgeConfig {
    boolean enabled = true;
    int port = 25585;
    String token;
    boolean autoStartMcdr = true;
    String pythonExecutable = "";
    boolean autoInstall = true;
    boolean onboardingDismissed = false;
    String onboardingLastClientId = "";

    static Path rootForGame(Path game) { return game.resolve("mcdr-singleplayer"); }
    static Path runtimeForGame(Path game) { return rootForGame(game).resolve("runtime"); }
    static Path configRootForGame(Path game) { return rootForGame(game); }
    static Path pathForGame(Path game) { return configRootForGame(game).resolve("mcdr-singleplayer-config.yml"); }

    static synchronized BridgeConfig loadForGame(Path game) throws IOException {
        Path runtime = runtimeForGame(game);
        if (Files.isSymbolicLink(rootForGame(game)) || Files.isSymbolicLink(runtime))
            throw new IOException("The mcdr-singleplayer configuration cannot be a link");
        Files.createDirectories(runtime);
        // Serialize first-install token creation and legacy migration across game processes.
        Path lockFile = runtime.resolve(".configuration.lock");
        if (Files.isSymbolicLink(lockFile)) throw new IOException("Configuration lock cannot be a link");
        try (var channel = java.nio.channels.FileChannel.open(lockFile,
                java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.WRITE);
             var lock = channel.lock(0, 1, false)) {
            return loadForGameLocked(game);
        }
    }

    private static BridgeConfig loadForGameLocked(Path game) throws IOException {
        Path path = pathForGame(game);
        Path root = rootForGame(game);
        for (String directory : new String[]{"log", "runtime"}) {
            Path child = root.resolve(directory);
            if (Files.isSymbolicLink(child)) throw new IOException("mcdr-singleplayer folders cannot be links");
            Files.createDirectories(child);
        }
        if (Files.isSymbolicLink(path.getParent()) || Files.isSymbolicLink(path)
                || Files.isSymbolicLink(root.resolve("config.json")))
            throw new IOException("The mcdr-singleplayer configuration cannot be a link");
        for (Path previousStatus : new Path[]{game.resolve("config/.mcdr_restore_progress.json"), runtimeForGame(game).resolve(".mcdr_restore_progress.json")}) {
          if (Files.isRegularFile(previousStatus)) {
            var state = com.google.gson.JsonParser.parseString(Files.readString(previousStatus)).getAsJsonObject();
            if (state.has("status") && "running".equals(state.get("status").getAsString())
                    && state.has("backend_pid") && ProcessHandle.of(state.get("backend_pid").getAsLong()).map(ProcessHandle::isAlive).orElse(false))
                throw new IOException("An old restore is running; wait for it to finish before migrating");
          }
        }
        migrateGroupedDirectories(root);
        Files.createDirectories(configRootForGame(game));
        Files.createDirectories(path.getParent());
        Path legacy = game.resolve("config/mcdr_singleplayer_bridge.json");
        Path oldRootConfig = root.resolve("config.json");
        if (!Files.exists(path)) {
            Path source = Files.isRegularFile(oldRootConfig) ? oldRootConfig : legacy;
            if (Files.isRegularFile(source)) {
                BridgeConfig old = load(source);
                writeConfig(path, old);
            }
        }
        if (Files.isRegularFile(legacy)) {
            if (Files.size(legacy) > 8192) throw new IOException("Legacy config exceeds limit");
            var old = com.google.gson.JsonParser.parseString(Files.readString(legacy)).getAsJsonObject();
            Path source = old.has("mcdrDirectory") && !old.get("mcdrDirectory").getAsString().isBlank()
                ? Path.of(old.get("mcdrDirectory").getAsString()) : game.resolve("mcdr2");
            // The old customized release could use this existing external server directory.
            Path previousDefault = Path.of("D:/我的世界/服务器/服务端/mcdr2");
            if (!Files.isDirectory(source) && Files.isRegularFile(previousDefault.resolve("config.yml"))) source = previousDefault;
            Path migration = runtimeForGame(game).resolve(".legacy-layout.json");
            if (Files.isDirectory(source) && !Files.exists(migration)) {
                var record = new com.google.gson.JsonObject();
                record.addProperty("source", source.toAbsolutePath().normalize().toString());
                Files.writeString(migration, record.toString());
            }
            preserveLegacy(legacy, runtimeForGame(game), "bridge-config-", ".json");
        }
        if (Files.isRegularFile(oldRootConfig)) {
            preserveLegacy(oldRootConfig, runtimeForGame(game), "config-json-", ".json");
        }
        for (String name : new String[]{".mcdr_restore_progress.json", ".mcdr_restore_locks.json", ".mcdr_bridge_session.json"}) {
            Path previous = game.resolve("config").resolve(name);
            Path target = runtimeForGame(game).resolve(name);
            if (Files.isRegularFile(previous)) {
                if (!Files.exists(target)) Files.move(previous, target);
                else {
                    if (name.equals(".mcdr_restore_locks.json")) {
                        var merged = new com.google.gson.JsonArray();
                        var names = new java.util.LinkedHashSet<String>();
                        for (Path lockFile : new Path[]{target, previous})
                            for (var value : com.google.gson.JsonParser.parseString(Files.readString(lockFile)).getAsJsonArray())
                                names.add(value.getAsString());
                        names.forEach(merged::add);
                        Files.writeString(target, merged.toString());
                    }
                    Path history = runtimeForGame(game).resolve("migration-history");
                    Files.createDirectories(history);
                    Files.move(previous, history.resolve(java.util.UUID.randomUUID() + "-" + name));
                }
            }
        }
        BridgeConfig config = load(path);
        // Leave current YAML untouched: another client's onboarding may update it.
        String current = Files.readString(path, StandardCharsets.UTF_8);
        if (current.stripLeading().startsWith("{") || current.contains("mcdrDirectory:")) writeConfig(path, config);
        return config;
    }

    private static void preserveLegacy(Path source, Path runtime, String prefix, String suffix) throws IOException {
        Path history = runtime.resolve("migration-history");
        if (Files.isSymbolicLink(history)) throw new IOException("Migration history cannot be a link");
        Files.createDirectories(history);
        Files.move(source, history.resolve(prefix + java.util.UUID.randomUUID() + suffix));
    }

    private static void migrateGroupedDirectories(Path root) throws IOException {
        Path runtime = root.resolve("runtime");
        Path oldData = root.resolve("data");
        Path oldProfiles = root.resolve("date");
        Path profiles = root.resolve("plugindata");
        if (Files.exists(oldProfiles, LinkOption.NOFOLLOW_LINKS)) {
            ensureControllerStopped(runtime);
            ensureTreeHasNoLinks(oldProfiles);
            if (Files.exists(profiles, LinkOption.NOFOLLOW_LINKS)) ensureTreeHasNoLinks(profiles);
            moveMerge(oldProfiles, profiles, runtime);
        }
        if (Files.exists(oldData, LinkOption.NOFOLLOW_LINKS)) {
            ensureControllerStopped(runtime);
            ensureTreeHasNoLinks(oldData);
            if (Files.exists(profiles, LinkOption.NOFOLLOW_LINKS)) ensureTreeHasNoLinks(profiles);
            moveMerge(oldData, profiles, runtime);
        }
        for (Path oldConfig : new Path[]{root.resolve("config"), runtime.resolve("config")}) {
            if (!Files.exists(oldConfig, LinkOption.NOFOLLOW_LINKS)) continue;
            if (Files.isSymbolicLink(oldConfig)) throw new IOException("Legacy shared config cannot be a link");
            for (String lockName : new String[]{".controller.lock", ".installation.lock"}) {
                Path lockFile = runtime.resolve(lockName);
                if (Files.exists(lockFile)) {
                    try (var channel = java.nio.channels.FileChannel.open(lockFile, java.nio.file.StandardOpenOption.WRITE)) {
                        try (var lock = channel.tryLock(0, 1, false)) {
                            if (lock == null) throw new IOException("MCDR is running; close the other client before migrating shared files");
                        } catch (java.nio.channels.OverlappingFileLockException e) {
                            throw new IOException("MCDR is running; shared configuration migration is blocked", e);
                        }
                    }
                }
            }
            try (var children = Files.list(oldConfig)) {
                for (Path child : children.toList()) {
                    String name = child.getFileName().toString();
                    if (java.util.Set.of("config.json", "config.yml", "permission.yml", "download-sources.json", "plugins").contains(name))
                        moveMerge(child, root.resolve(name), runtime);
                    else moveMerge(child, runtime.resolve("legacy-files/shared-config").resolve(name), runtime);
                }
            }
            Files.delete(oldConfig);
        }
        if (Files.isSymbolicLink(profiles)) throw new IOException("Per-save plugin data cannot be a link");
        Files.createDirectories(profiles);
    }

    private static void ensureControllerStopped(Path runtime) throws IOException {
        for (String lockName : new String[]{".controller.lock", ".installation.lock"}) {
            Path lockFile = runtime.resolve(lockName);
            if (!Files.exists(lockFile, LinkOption.NOFOLLOW_LINKS)) continue;
            try (var channel = java.nio.channels.FileChannel.open(lockFile, java.nio.file.StandardOpenOption.WRITE)) {
                try (var lock = channel.tryLock(0, 1, false)) {
                    if (lock == null) throw new IOException("MCDR is running; close the other client before migrating per-save data");
                } catch (java.nio.channels.OverlappingFileLockException e) {
                    throw new IOException("MCDR is running; per-save data migration is blocked", e);
                }
            }
        }
    }

    private static void ensureTreeHasNoLinks(Path root) throws IOException {
        if (Files.isSymbolicLink(root)) throw new IOException("Per-save data migration cannot follow links");
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) return;
        try (var paths = Files.walk(root)) {
            for (Path path : paths.toList())
                if (Files.isSymbolicLink(path)) throw new IOException("Per-save data migration cannot follow links");
        }
    }

    private static void moveMerge(Path source, Path target, Path runtime) throws IOException {
        if (Files.isSymbolicLink(source)) throw new IOException("Legacy MCDR folders cannot be links");
        if (Files.isSymbolicLink(target)) throw new IOException("MCDR migration destination cannot be a link");
        if (!Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
            Files.move(source, target);
            return;
        }
        if (Files.isDirectory(source, LinkOption.NOFOLLOW_LINKS) && Files.isDirectory(target, LinkOption.NOFOLLOW_LINKS)) {
            try (var children = Files.list(source)) {
                for (Path child : children.toList()) moveMerge(child, target.resolve(child.getFileName()), runtime);
            }
            Files.delete(source);
            return;
        }
        if (Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS) && Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)
                && java.util.Arrays.equals(Files.readAllBytes(source), Files.readAllBytes(target))) {
            Files.delete(source);
            return;
        }
        Path history = runtime.resolve("migration-history");
        if (Files.isSymbolicLink(history)) throw new IOException("Migration history cannot be a link");
        Files.createDirectories(history);
        Files.move(source, history.resolve(java.util.UUID.randomUUID() + "-" + source.getFileName()));
    }

    static BridgeConfig load(Path path) throws IOException {
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        BridgeConfig config;
        if (Files.exists(path)) {
            if (Files.size(path) > 8192) throw new IOException("Bridge config exceeds limit");
            String text = Files.readString(path, StandardCharsets.UTF_8);
            config = text.stripLeading().startsWith("{") || path.getFileName().toString().toLowerCase().endsWith(".json")
                    ? gson.fromJson(text, BridgeConfig.class) : fromYaml(text, gson);
        } else {
            config = new BridgeConfig();
            byte[] random = new byte[32];
            new SecureRandom().nextBytes(random);
            config.token = HexFormat.of().formatHex(random);
            Files.createDirectories(path.getParent());
            writeConfig(path, config);
        }
        if (config == null || config.port < 1 || config.port > 65535
                || config.token == null || config.token.length() < 32 || config.token.length() > 256) {
            throw new IOException("Invalid bridge configuration");
        }
        return config;
    }

    private static BridgeConfig fromYaml(String text, Gson gson) throws IOException {
        var values = new com.google.gson.JsonObject();
        int lineNumber = 0;
        for (String line : text.split("\\R")) {
            lineNumber++;
            String stripped = line.strip();
            if (stripped.isEmpty() || stripped.startsWith("#")) continue;
            int separator = stripped.indexOf(':');
            if (separator <= 0) throw new IOException("Invalid bridge YAML at line " + lineNumber);
            String key = stripped.substring(0, separator).strip();
            String raw = stripYamlComment(stripped.substring(separator + 1).strip());
            try {
                com.google.gson.JsonElement value;
                if (raw.startsWith("\"") || raw.startsWith("[") || raw.startsWith("{"))
                    value = com.google.gson.JsonParser.parseString(raw);
                else if (raw.equals("true") || raw.equals("false") || raw.matches("-?[0-9]+"))
                    value = com.google.gson.JsonParser.parseString(raw);
                else value = new com.google.gson.JsonPrimitive(raw.split(" #", 2)[0].strip());
                values.add(key, value);
            } catch (RuntimeException exception) {
                throw new IOException("Invalid bridge YAML at line " + lineNumber, exception);
            }
        }
        return gson.fromJson(values, BridgeConfig.class);
    }

    private static String stripYamlComment(String value) {
        char quote = 0;
        boolean escaped = false;
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (escaped) escaped = false;
            else if (current == '\\' && quote == '"') escaped = true;
            else if (quote != 0 && current == quote) quote = 0;
            else if (quote == 0 && (current == '"' || current == '\'')) quote = current;
            else if (quote == 0 && current == '#' && (index == 0 || Character.isWhitespace(value.charAt(index - 1))))
                return value.substring(0, index).stripTrailing();
        }
        return value;
    }

    private static void writeConfig(Path path, BridgeConfig config) throws IOException {
        if (path.getFileName().toString().toLowerCase().endsWith(".json")) {
            Files.writeString(path, new GsonBuilder().setPrettyPrinting().create().toJson(config) + "\n", StandardCharsets.UTF_8);
            return;
        }
        Gson gson = new Gson();
        String contents = """
                # MCDR Singleplayer bridge settings / 单人游戏 MCDR 桥接设置
                # These settings apply to this game instance; plugin data remains separated by save.
                # 本设置作用于当前游戏实例；各存档的插件配置和数据仍分别保存在 plugindata/<存档文件夹名>。
                # Edit values below, then restart the game to apply changes.
                # 修改下列数值后重启游戏生效。
                # 启用单人游戏与 MCDR 的桥接
                enabled: %s
                # 本机回环连接端口；发生冲突时可修改
                port: %s
                # 随机身份验证令牌，请勿分享或公开
                token: %s
                # 进入单人存档时自动启动 MCDR
                autoStartMcdr: %s
                # 可选的 Python 可执行文件路径；留空时自动检测
                pythonExecutable: %s
                # 自动准备 MCDR、桥接插件及运行依赖
                autoInstall: %s
                # 是否隐藏首次使用提示
                onboardingDismissed: %s
                # 上次显示提示的客户端标识，由模组维护
                onboardingLastClientId: %s
                """.formatted(config.enabled, config.port, gson.toJson(config.token), config.autoStartMcdr,
                        gson.toJson(config.pythonExecutable), config.autoInstall, config.onboardingDismissed,
                        gson.toJson(config.onboardingLastClientId));
        Files.writeString(path, contents, StandardCharsets.UTF_8);
    }
}
