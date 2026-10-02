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

    static Path rootForGame(Path game) { return game.resolve("mcdr-singleplayer"); }
    static Path runtimeForGame(Path game) { return rootForGame(game).resolve("runtime"); }
    static Path configRootForGame(Path game) { return runtimeForGame(game).resolve("config"); }
    static Path pathForGame(Path game) { return configRootForGame(game).resolve("config.json"); }

    static BridgeConfig loadForGame(Path game) throws IOException {
        Path path = pathForGame(game);
        Path root = rootForGame(game);
        for (String directory : new String[]{"date", "log", "runtime"}) {
            Path child = root.resolve(directory);
            if (Files.isSymbolicLink(child)) throw new IOException("mcdr-singleplayer folders cannot be links");
            Files.createDirectories(child);
        }
        if (Files.isSymbolicLink(path.getParent()) || Files.isSymbolicLink(path))
            throw new IOException("The mcdr-singleplayer configuration cannot be a link");
        Path previousStatus = game.resolve("config/.mcdr_restore_progress.json");
        if (Files.isRegularFile(previousStatus)) {
            var state = com.google.gson.JsonParser.parseString(Files.readString(previousStatus)).getAsJsonObject();
            if (state.has("status") && "running".equals(state.get("status").getAsString())
                    && state.has("backend_pid") && ProcessHandle.of(state.get("backend_pid").getAsLong()).map(ProcessHandle::isAlive).orElse(false))
                throw new IOException("An old restore is running; wait for it to finish before migrating");
        }
        migrateGroupedDirectories(root);
        Files.createDirectories(configRootForGame(game));
        Files.createDirectories(path.getParent());
        Path legacy = game.resolve("config/mcdr_singleplayer_bridge.json");
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
            if (!Files.exists(path)) Files.move(legacy, path);
            else {
                Path history = runtimeForGame(game).resolve("migration-history");
                Files.createDirectories(history);
                Files.move(legacy, history.resolve("bridge-config-" + java.util.UUID.randomUUID() + ".json"));
            }
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
        // Remove retired external-directory settings from the canonical config.
        Files.writeString(path, new GsonBuilder().setPrettyPrinting().create().toJson(config) + "\n");
        return config;
    }

    private static void migrateGroupedDirectories(Path root) throws IOException {
        Path runtime = root.resolve("runtime");
        Path config = runtime.resolve("config");
        Path oldConfig = root.resolve("config");
        Path oldData = root.resolve("data");
        Files.createDirectories(config);
        if (Files.exists(oldConfig, LinkOption.NOFOLLOW_LINKS)) moveMerge(oldConfig, config, runtime);
        for (String name : new String[]{"config.json", "config.yml", "permission.yml", "download-sources.json"}) {
            Path legacyFile = root.resolve(name);
            if (Files.exists(legacyFile, LinkOption.NOFOLLOW_LINKS)) moveMerge(legacyFile, config.resolve(name), runtime);
        }
        if (Files.exists(oldData, LinkOption.NOFOLLOW_LINKS)) moveMerge(oldData, root.resolve("date"), runtime);
    }

    private static void moveMerge(Path source, Path target, Path runtime) throws IOException {
        if (Files.isSymbolicLink(source)) throw new IOException("Legacy MCDR folders cannot be links");
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
        Files.createDirectories(history);
        Files.move(source, history.resolve(java.util.UUID.randomUUID() + "-" + source.getFileName()));
    }

    static BridgeConfig load(Path path) throws IOException {
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        BridgeConfig config;
        if (Files.exists(path)) {
            if (Files.size(path) > 8192) throw new IOException("Bridge config exceeds limit");
            config = gson.fromJson(Files.readString(path, StandardCharsets.UTF_8), BridgeConfig.class);
        } else {
            config = new BridgeConfig();
            byte[] random = new byte[32];
            new SecureRandom().nextBytes(random);
            config.token = HexFormat.of().formatHex(random);
            Files.createDirectories(path.getParent());
            Files.writeString(path, gson.toJson(config) + "\n", StandardCharsets.UTF_8);
        }
        if (config == null || config.port < 1 || config.port > 65535
                || config.token == null || config.token.length() < 32 || config.token.length() > 256) {
            throw new IOException("Invalid bridge configuration");
        }
        return config;
    }
}
