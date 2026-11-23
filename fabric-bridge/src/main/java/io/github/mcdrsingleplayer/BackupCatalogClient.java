package io.github.mcdrsingleplayer;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;

/**
 * 用私有解释器读取一个存档的备份库，并执行离线恢复；全部在虚拟线程里跑，
 * 不占用渲染线程。
 *
 * 三个备份库（Prime Backup、Chunk Backup、原版）各自独立读取，一个库失败不会
 * 影响其它两个。原版备份不依赖任何插件配置。
 */
final class BackupCatalogClient {
    /** 一个可回档的备份；{@code ref} 是交给离线命令的选择符。 */
    record Entry(String ref, String kind, String date, String comment, String operator,
            List<String> dimensions, long size, boolean safety, boolean restorable, String reason) {
        boolean prime() { return kind.equals("prime"); }
        boolean vanilla() { return kind.equals("vanilla"); }
    }

    /** 一个备份库；失败原因跟着库本身，不会遮住别的库。 */
    record Store(List<Entry> entries, String error) {}

    record Catalog(Store prime, Store chunk, Store vanilla) {}

    static void load(String world, Consumer<Catalog> callback) {
        Thread.ofVirtual().name("mcdr-backup-catalog").start(() -> {
            Catalog catalog;
            try {
                catalog = parse(run(world, "--catalog"));
            } catch (Exception e) {
                String error = message(e);
                catalog = new Catalog(new Store(List.of(), error), new Store(List.of(), error),
                    new Store(List.of(), error));
            }
            Catalog delivered = catalog;
            Minecraft.getInstance().execute(() -> callback.accept(delivered));
        });
    }

    static void restore(String world, String ref, Consumer<String> onFailure) {
        Thread.ofVirtual().name("mcdr-backup-restore").start(() -> {
            String error = "";
            try {
                String[] operation;
                if (ref.startsWith("chunk:")) operation = new String[] {"--chunk-restore", ref};
                else if (ref.startsWith("vanilla:")) operation = new String[] {"--vanilla-restore", ref};
                else operation = new String[] {"--restore", ref.substring("prime:".length())};
                JsonObject response = run(world, operation);
                error = failure(response);
            } catch (Exception e) {
                error = message(e);
            }
            deliver(onFailure, error);
        });
    }

    /** 原版备份：用原版自己的格式立刻创建一份。 */
    static void createVanilla(String world, Consumer<String> onDone) {
        runCreate(world, "--vanilla-create", onDone);
    }

    /** PB / CB 备份：两者都能在游戏关闭时离线创建。 */
    static void create(String world, boolean chunk, Consumer<String> onDone) {
        create(world, chunk, "", "", null, onDone);
    }

    /**
     * 建一份 PB 或 CB 备份。
     *
     * PB 只接备注；CB 还能限定维度与区块范围（对应上游 pmake 的选区），
     * 选区的四个数字是 x1 z1 x2 z2，两个角点顺序随意。
     */
    static void create(String world, boolean chunk, String comment, String dimension,
            int[] region, Consumer<String> onDone) {
        Thread.ofVirtual().name("mcdr-backup-create").start(() -> {
            String error = "";
            try {
                var operation = new ArrayList<String>(List.of("--make", chunk ? "chunk" : "prime"));
                if (!comment.isEmpty()) operation.addAll(List.of("--comment", comment));
                if (chunk && dimension != null && !dimension.isEmpty())
                    operation.addAll(List.of("--dimension", dimension));
                if (chunk && region != null && region.length == 4)
                    operation.addAll(List.of("--region",
                        region[0] + "," + region[1] + "," + region[2] + "," + region[3]));
                error = failure(run(world, operation.toArray(String[]::new)));
            } catch (Exception e) {
                error = message(e);
            }
            deliver(onDone, error);
        });
    }

    private static void runCreate(String world, String operation, Consumer<String> onDone) {
        Thread.ofVirtual().name("mcdr-backup-create").start(() -> {
            String error = "";
            try {
                error = failure(run(world, operation));
            } catch (Exception e) {
                error = message(e);
            }
            deliver(onDone, error);
        });
    }

    /** 为当前存档补一份备份插件配置；只写配置，不装插件。 */
    static void setup(String world, boolean chunk, Consumer<String> onDone) {
        Thread.ofVirtual().name("mcdr-backup-setup").start(() -> {
            String error = "";
            try {
                error = failure(run(world, "--setup", chunk ? "chunk" : "prime"));
            } catch (Exception e) {
                error = message(e);
            }
            deliver(onDone, error);
        });
    }

    /** 打开备份库所在目录，方便手动管理其中的文件。 */
    static void open(String world, String kind, Consumer<String> onDone) {
        Thread.ofVirtual().name("mcdr-backup-open").start(() -> {
            String error = "";
            try {
                String key = switch (kind) {
                    case "prime" -> "prime";
                    case "chunk" -> "chunk";
                    default -> "vanilla";
                };
                JsonObject response = run(world, "--paths", key);
                if (response.has("error")) error = response.get("error").getAsString();
                else {
                    Path folder = Path.of(response.get("path").getAsString());
                    Files.createDirectories(folder);
                    String target = folder.toString();
                    Minecraft.getInstance().execute(() -> openFolder(target));
                }
            } catch (Exception e) {
                error = message(e);
            }
            deliver(onDone, error);
        });
    }

    private static void openFolder(String path) {
        try {
            Path folder = Path.of(path);
            boolean windows = System.getProperty("os.name", "").toLowerCase().contains("windows");
            if (windows) new ProcessBuilder("explorer.exe", folder.toString()).start();
            else if (System.getProperty("os.name", "").toLowerCase().contains("mac"))
                new ProcessBuilder("open", folder.toString()).start();
            else new ProcessBuilder("xdg-open", folder.toString()).start();
        } catch (Exception ignored) {
            // 打不开目录不该影响界面；调用方已经拿到空错误，可以用按钮重试。
        }
    }

    /** 空字符串表示成功；失败时返回可直接翻译的键或文本。 */
    private static String failure(JsonObject response) {
        if (response.has("error")) return response.get("error").getAsString();
        if (!response.has("completed") || !response.get("completed").getAsBoolean())
            return "mcdr-singleplayer.catalog.no_response";
        return "";
    }

    private static void deliver(Consumer<String> callback, String error) {
        if (error.isEmpty()) {
            Minecraft.getInstance().execute(() -> callback.accept(""));
            return;
        }
        String delivered = error;
        Minecraft.getInstance().execute(() -> callback.accept(delivered));
    }

    private static String message(Exception exception) {
        return exception.getMessage() == null ? exception.getClass().getSimpleName() : exception.getMessage();
    }

    static Catalog parse(JsonObject response) {
        return new Catalog(store(response, "prime"), store(response, "chunk"), store(response, "vanilla"));
    }

    private static Store store(JsonObject response, String key) {
        if (!response.has(key) || !response.get(key).isJsonObject()) return new Store(List.of(), "");
        JsonObject value = response.getAsJsonObject(key);
        String error = text(value, "error");
        var entries = new ArrayList<Entry>();
        JsonArray rows = value.has("backups") && value.get("backups").isJsonArray()
            ? value.getAsJsonArray("backups") : new JsonArray();
        for (var item : rows) {
            // 没有身份的行无法回档，直接跳过而不是列出半条。
            if (!item.isJsonObject()) continue;
            JsonObject row = item.getAsJsonObject();
            String ref = text(row, "ref");
            if (ref.isEmpty()) continue;
            var dimensions = new ArrayList<String>();
            if (row.has("dimensions") && row.get("dimensions").isJsonArray())
                for (var dimension : row.getAsJsonArray("dimensions"))
                    if (dimension.isJsonPrimitive()) dimensions.add(dimension.getAsString());
            entries.add(new Entry(
                ref,
                row.has("kind") && row.get("kind").isJsonPrimitive() ? row.get("kind").getAsString() : key,
                text(row, "date"),
                text(row, "comment"),
                text(row, "operator"),
                List.copyOf(dimensions),
                row.has("size") && row.get("size").isJsonPrimitive() ? row.get("size").getAsLong() : 0,
                row.has("temporary") && row.get("temporary").isJsonPrimitive() && row.get("temporary").getAsBoolean(),
                !row.has("restorable") || !row.get("restorable").isJsonPrimitive() || row.get("restorable").getAsBoolean(),
                text(row, "reason")));
        }
        return new Store(List.copyOf(entries), error);
    }

    /** 缺字段或类型不对时读成空值，而不是让整个备份库失败。 */
    private static String text(JsonObject value, String key) {
        return value.has(key) && value.get(key).isJsonPrimitive() ? value.get(key).getAsString() : "";
    }

    private static JsonObject run(String world, String... operation) throws Exception {
        Path game = FabricLoader.getInstance().getGameDir();
        Path common = BridgeConfig.rootForGame(game);
        Path python = common.resolve(System.getProperty("os.name", "").toLowerCase().contains("windows")
            ? "runtime/.bridge-venv/Scripts/python.exe" : "runtime/.bridge-venv/bin/python");
        Path script = common.resolve("runtime/bridge-runtime/bridge_restore.py");
        if (!Files.isRegularFile(python) || !Files.isRegularFile(script))
            throw new IllegalStateException("mcdr-singleplayer.catalog.runtime_missing");
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
        if (output.length() > 4194304) throw new IllegalStateException("mcdr-singleplayer.catalog.response_too_large");
        if (output.isEmpty()) throw new IllegalStateException("mcdr-singleplayer.catalog.no_response");
        JsonObject response = JsonParser.parseString(output).getAsJsonObject();
        if (exit != 0 && !response.has("error")) throw new IllegalStateException("mcdr-singleplayer.catalog.no_response");
        return response;
    }
}
