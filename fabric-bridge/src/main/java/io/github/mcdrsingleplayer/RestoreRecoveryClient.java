package io.github.mcdrsingleplayer;

import com.google.gson.JsonParser;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

/** Runs the pinned PB CLI in the private environment, never on the render thread. */
final class RestoreRecoveryClient {
    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    record Backup(int id, long timestamp, String comment, boolean temporary) {
        Component label() {
            String date = DATE.format(Instant.ofEpochSecond(timestamp).atZone(ZoneId.systemDefault()));
            String shortComment = comment.length() > 36 ? comment.substring(0, 36) + "…" : comment;
            if (temporary) return Component.empty().append(Component.literal("#" + id + "  " + date + "  "))
                .append(Component.translatable("mcdr-singleplayer.restore.retry.safety_backup", id));
            return Component.literal("#" + id + "  " + date + "  " + shortComment);
        }
    }

    record Result(List<Backup> backups, String error) {}

    static void list(String world, Consumer<Result> callback) {
        Thread.ofVirtual().name("mcdr-restore-list").start(() -> {
            Result result;
            try {
                var response = run(world, "--list");
                if (response.has("error")) throw new IllegalStateException(response.get("error").getAsString());
                var entries = new ArrayList<Backup>();
                for (var item : response.getAsJsonArray("backups")) {
                    var value = item.getAsJsonObject();
                    entries.add(new Backup(value.get("id").getAsInt(), value.get("timestamp").getAsLong(),
                        value.get("comment").getAsString(), value.get("temporary").getAsBoolean()));
                }
                result = new Result(List.copyOf(entries), "");
            } catch (Exception e) {
                result = new Result(List.of(), e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());
            }
            Result delivered = result;
            Minecraft.getInstance().execute(() -> callback.accept(delivered));
        });
    }

    static void restore(String world, int backupId, Consumer<String> onFailure) {
        Thread.ofVirtual().name("mcdr-restore-retry").start(() -> {
            String error = "";
            try {
                var response = run(world, "--restore", Integer.toString(backupId));
                if (response.has("error")) error = response.get("error").getAsString();
                else if (!response.has("completed") || !response.get("completed").getAsBoolean())
                    error = "Offline restoration did not report completion";
            } catch (Exception e) {
                error = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            }
            if (!error.isEmpty()) {
                String delivered = error;
                Minecraft.getInstance().execute(() -> onFailure.accept(delivered));
            }
        });
    }

    private static com.google.gson.JsonObject run(String world, String... operation) throws Exception {
        Path game = FabricLoader.getInstance().getGameDir();
        Path common = BridgeConfig.rootForGame(game);
        Path python = common.resolve(System.getProperty("os.name", "").toLowerCase().contains("windows")
            ? "runtime/.bridge-venv/Scripts/python.exe" : "runtime/.bridge-venv/bin/python");
        Path script = common.resolve("runtime/bridge-runtime/bridge_restore.py");
        if (!Files.isRegularFile(python) || !Files.isRegularFile(script))
            throw new IllegalStateException("MCDR runtime is not installed; restart Minecraft after installing Python");
        var command = new ArrayList<String>();
        command.add(python.toString());
        command.add(script.toString());
        command.addAll(List.of("--common", common.toString(), "--world", world));
        command.addAll(List.of(operation));
        Path log = common.resolve("log/recovery-client.log");
        Files.createDirectories(log.getParent());
        var process = new ProcessBuilder(command).redirectError(ProcessBuilder.Redirect.appendTo(log.toFile())).start();
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).strip();
        int exit = process.waitFor();
        if (output.length() > 1048576) throw new IllegalStateException("Offline restore response is too large");
        if (output.isEmpty()) throw new IllegalStateException("Offline restore exited " + exit + "; see log/recovery-client.log");
        var response = JsonParser.parseString(output).getAsJsonObject();
        if (exit != 0 && !response.has("error"))
            throw new IllegalStateException("Offline restore exited " + exit + "; see log/recovery-client.log");
        return response;
    }
}
