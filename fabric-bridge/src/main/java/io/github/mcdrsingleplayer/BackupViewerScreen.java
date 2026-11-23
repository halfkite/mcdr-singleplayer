package io.github.mcdrsingleplayer;

import java.util.List;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.chat.Component;

/**
 * 浏览并回档一个存档的三类备份：Prime Backup、Chunk Backup 与游戏原版备份。
 *
 * 打开编辑界面时存档锁被它持有，所以回档前先关掉编辑界面释放 session.lock，
 * 再让离线流程动文件。三个备份库各自独立读取，一个库缺失只显示该页的原因。
 *
 * 版面铺满游戏窗口：宽度按窗口取，列表行数按剩余高度算。各行 y 由 headerY() 一路
 * 推出来，渲染与布局共用同一套坐标，所以文字不会压在按钮上；窗口很矮时列表会自动
 * 少显示几行而不是把文字挤出去。
 *
 * 建备份前先收备注（PB）或维度与区块选区（CB），建的过程中显示进度提示。
 */
public final class BackupViewerScreen extends Screen {
    private static final int ROW_HEIGHT = 20;
    private static final int MIN_WIDTH = 340;
    private static final int MIN_ROWS = 2;
    private static final int MAX_ROWS = 9;
    private static final String[] TABS = {"prime", "chunk", "vanilla"};
    private final String world;
    private final Screen parent;
    private final BackupCatalogClient.Catalog catalog;
    private final String error;
    private final String tab;
    private final int page;
    private final String selected;
    private final boolean armed;
    private boolean loading;
    private boolean working;

    BackupViewerScreen(String world, Screen parent) {
        this(world, parent, null, "", "prime", 0, "", false);
    }

    /** 编辑界面的入口；parent 是回退目标。 */
    public static void open(String world, Screen parent) {
        Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent));
    }

    private BackupViewerScreen(String world, Screen parent, BackupCatalogClient.Catalog catalog, String error,
            String tab, int page, String selected, boolean armed) {
        super(Component.translatable("mcdr-singleplayer.backup.viewer.title"));
        this.world = world;
        this.parent = parent;
        this.catalog = catalog;
        this.error = error;
        this.tab = tab;
        this.page = page;
        this.selected = selected;
        this.armed = armed;
    }

    private BackupCatalogClient.Store store() {
        return switch (tab) {
            case "chunk" -> catalog.chunk();
            case "vanilla" -> catalog.vanilla();
            default -> catalog.prime();
        };
    }

    private List<BackupCatalogClient.Entry> entries() {
        return store().entries();
    }

    private BackupCatalogClient.Entry chosen() {
        if (catalog == null) return null;
        for (var entry : entries()) if (entry.ref().equals(selected)) return entry;
        return null;
    }

    private BackupViewerScreen with(String nextTab, int nextPage, String nextSelected, boolean nextArmed) {
        return new BackupViewerScreen(world, parent, catalog, error, nextTab, nextPage, nextSelected, nextArmed);
    }

    /** 铺满窗口：左右各留一点边距，宽屏时不至于拉成一条。 */
    private int column() {
        return Math.max(MIN_WIDTH, Math.min(width - 40, Math.max(width - 120, 520)));
    }

    private int left() {
        return width / 2 - column() / 2;
    }

    /** 列表行数按窗口高度自适应，至少两行，至多九行。 */
    private int rows() {
        int reserved = 16 + 26 + 26 + 26 + 24 + toolRows() * 24 + 12 + 18 + 26 + 16;
        int available = Math.max(0, height - reserved);
        return Math.max(MIN_ROWS, Math.min(MAX_ROWS, available / (ROW_HEIGHT + 2)));
    }

    private int toolRows() {
        // 打开备份文件夹 + 建立备份；配置缺失时再加一行创建配置。
        if (catalog == null) return 0;
        return store().error().isEmpty() || tab.equals("vanilla") ? 2 : 3;
    }

    private int top() {
        int total = 16 + 26 + rows() * (ROW_HEIGHT + 2) + 26 + 26 + 24
            + toolRows() * 24 + 12 + 18 + 26;
        return Math.max(6, (height - total) / 2);
    }

    private int tabsY() { return top() + 16; }
    private int listY() { return tabsY() + 26; }
    private int pagerY() { return listY() + rows() * (ROW_HEIGHT + 2) + 2; }
    private int noteY() { return pagerY() + 26; }
    private int toolsY() { return noteY() + 26; }
    private int warningY() { return toolsY() + toolRows() * 24 + 12; }
    private int footerY() { return warningY() + 18; }
    private int errorY() { return footerY() + 26; }

    @Override protected void init() {
        int column = column();
        int x = left();
        int tabWidth = (column - 8) / 3;
        for (int index = 0; index < TABS.length; index++) {
            String kind = TABS[index];
            addRenderableWidget(Button.builder(tab(kind), button -> switchStore(kind))
                .bounds(x + index * (tabWidth + 4), tabsY(), tabWidth, ROW_HEIGHT).build());
        }
        if (catalog == null) {
            if (!loading) {
                loading = true;
                BackupCatalogClient.load(world, result -> {
                    if (Minecraft.getInstance().gui.screen() == this)
                        Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, result, "",
                            tab, 0, "", false));
                });
            }
        } else {
            int limit = Math.min(rows(), Math.max(0, entries().size() - page * rows()));
            for (int offset = 0; offset < limit; offset++) {
                var entry = entries().get(page * rows() + offset);
                String label = (entry.ref().equals(selected) ? "> " : "") + row(entry);
                addRenderableWidget(Button.builder(Component.literal(label), button ->
                    Minecraft.getInstance().gui.setScreen(with(tab, page, entry.ref(), false)))
                    .bounds(x, listY() + offset * (ROW_HEIGHT + 2), column, ROW_HEIGHT).build());
            }
            var previous = addRenderableWidget(Button.builder(Component.literal("<"), button ->
                Minecraft.getInstance().gui.setScreen(with(tab, page - 1, selected, false)))
                .bounds(x, pagerY(), 32, ROW_HEIGHT).build());
            previous.active = page > 0;
            var next = addRenderableWidget(Button.builder(Component.literal(">"), button ->
                Minecraft.getInstance().gui.setScreen(with(tab, page + 1, selected, false)))
                .bounds(x + column - 32, pagerY(), 32, ROW_HEIGHT).build());
            next.active = (page + 1) * rows() < entries().size();

            int tools = toolsY();
            boolean configured = store().error().isEmpty();
            var make = addRenderableWidget(Button.builder(
                Component.translatable("mcdr-singleplayer.backup.viewer.make_backup." + tab),
                button -> makeBackup()).bounds(x, tools, column, ROW_HEIGHT).build());
            make.active = configured && !working;
            tools += 24;
            if (!tab.equals("vanilla") && !configured) {
                addRenderableWidget(Button.builder(
                    Component.translatable("mcdr-singleplayer.backup.viewer.create_config"),
                    button -> createConfig()).bounds(x, tools, column, ROW_HEIGHT).build());
                tools += 24;
            }
            addRenderableWidget(Button.builder(
                Component.translatable("mcdr-singleplayer.backup.viewer.open_folder"), button -> openFolder())
                .bounds(x, tools, column, ROW_HEIGHT).build());
        }
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.back"), button ->
            onClose()).bounds(x, footerY(), 100, ROW_HEIGHT).build());
        var chosen = chosen();
        var confirm = addRenderableWidget(Button.builder(
            Component.translatable(armed ? "mcdr-singleplayer.backup.viewer.confirm_armed"
                : "mcdr-singleplayer.backup.viewer.confirm"), button -> restore())
            .bounds(x + 104, footerY(), column - 104, ROW_HEIGHT).build());
        confirm.active = chosen != null && chosen.restorable() && error.isEmpty() && !working;
    }

    /** 一个标签页；当前页用 » 前缀区分。 */
    private Component tab(String kind) {
        Component label = Component.translatable("mcdr-singleplayer.backup.viewer.tab." + kind, count(kind));
        return tab.equals(kind)
            ? Component.empty().append(Component.literal("» ")).append(label) : label;
    }

    private int count(String kind) {
        if (catalog == null) return 0;
        return switch (kind) {
            case "chunk" -> catalog.chunk().entries().size();
            case "vanilla" -> catalog.vanilla().entries().size();
            default -> catalog.prime().entries().size();
        };
    }

    private void switchStore(String nextTab) {
        if (catalog == null) return;
        String nextError = switch (nextTab) {
            case "chunk" -> catalog.chunk().error();
            case "vanilla" -> catalog.vanilla().error();
            default -> catalog.prime().error();
        };
        Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, catalog, nextError,
            nextTab, 0, "", false));
    }

    private void createConfig() {
        if (working) return;
        working = true;
        BackupCatalogClient.setup(world, tab.equals("chunk"), failure -> {
            if (Minecraft.getInstance().gui.screen() != this) return;
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent,
                failure.isEmpty() ? null : catalog, failure, tab, 0, "", false));
        });
    }

    /**
     * 建备份：先收备注（PB）或维度与选区（CB），再交给离线流程，期间显示进度。
     */
    private void makeBackup() {
        if (working || catalog == null || !store().error().isEmpty()) return;
        if (tab.equals("vanilla")) {
            runCreate("", null, "");
            return;
        }
        if (tab.equals("chunk")) {
            ChunkBackupScreen.open(this, dimensions(), (dimension, region, comment) -> {
                if (dimension == null) return;  // 取消
                runCreate(comment, dimension, region == null ? "" : join(region));
            });
            return;
        }
        BackupCommentScreen.open(this, "mcdr-singleplayer.backup.viewer.make_backup.prime",
            comment -> {
                if (comment == null) return;  // 取消
                runCreate(comment, null, "");
            });
    }

    private static String join(int[] region) {
        return region[0] + "," + region[1] + "," + region[2] + "," + region[3];
    }

    /** 当前存档 CB 配置里声明的维度，供选区界面切换。 */
    private List<String> dimensions() {
        var chosen = chosen();
        if (chosen != null && !chosen.dimensions().isEmpty()) return chosen.dimensions();
        // 列表为空时给常见维度，备份器会用配置里的维度表校验。
        return List.of("minecraft:overworld", "minecraft:the_nether", "minecraft:the_end");
    }

    private void runCreate(String comment, String dimension, String region) {
        int[] bounds = null;
        if (region != null && !region.isEmpty()) {
            var parts = region.split(",");
            bounds = new int[parts.length];
            for (int index = 0; index < parts.length; index++) bounds[index] = Integer.parseInt(parts[index]);
        }
        int[] region_bounds = bounds;
        // 进度提示由 working 标记在标题下方显示，直到任务返回。
        java.util.function.Consumer<String> done = failure -> {
            if (!(Minecraft.getInstance().gui.screen() instanceof BackupViewerScreen)) return;
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent,
                failure.isEmpty() ? null : catalog, failure, tab, 0, "", false));
        };
        working = true;
        if (Minecraft.getInstance().gui.screen() == this)
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, catalog, error,
                tab, page, selected, false));
        if (tab.equals("vanilla")) {
            BackupCatalogClient.createVanilla(world, done);
            return;
        }
        BackupCatalogClient.create(world, tab.equals("chunk"), comment == null ? "" : comment,
            dimension, region_bounds, done);
    }

    private void openFolder() {
        BackupCatalogClient.open(world, tab, failure -> {
            if (failure.isEmpty() || Minecraft.getInstance().gui.screen() != this) return;
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, catalog, failure,
                tab, page, selected, false));
        });
    }

    private static String row(BackupCatalogClient.Entry entry) {
        String comment = entry.comment();
        if (comment.length() > 30) comment = comment.substring(0, 30) + "…";
        String tag = switch (entry.kind()) {
            case "prime" -> entry.safety() ? "P*" : "P";
            case "vanilla" -> "V";
            default -> "C";
        };
        return tag + "  " + entry.date() + "  " + comment;
    }

    private void restore() {
        var chosen = chosen();
        if (catalog == null || chosen == null || !chosen.restorable() || !error.isEmpty() || working) return;
        if (RestoreProgressMonitor.blocks(world)) {
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, catalog,
                "mcdr-singleplayer.backup.viewer.busy", tab, page, selected, false));
            return;
        }
        if (!armed) {
            Minecraft.getInstance().gui.setScreen(with(tab, page, selected, true));
            return;
        }
        if (parent instanceof net.minecraft.client.gui.screens.worldselection.EditWorldScreen) parent.onClose();
        Minecraft.getInstance().gui.setScreen(new TitleScreen());
        BackupCatalogClient.restore(world, chosen.ref(), reason -> {
            if (Minecraft.getInstance().gui.screen() instanceof TitleScreen)
                Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, null, null, reason,
                    "prime", 0, "", false));
        });
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float ticks) {
        int column = column();
        graphics.fill(0, 0, width, height, 0xc0000000);
        graphics.centeredText(font, title, width / 2, top(), 0xffffffff);
        graphics.centeredText(font, Component.literal(world), width / 2, top() + 11, 0xff808080);
        // 备份进行中：在标题下面显示进度，避免看起来像卡住。
        if (working) {
            graphics.centeredText(font, Component.translatable("mcdr-singleplayer.backup.viewer.progress"),
                width / 2, tabsY() + 4, 0xffffcc66);
        }

        int centre = listY() + (rows() * (ROW_HEIGHT + 2)) / 2 - 4;
        if (catalog == null) {
            graphics.centeredText(font, Component.translatable("mcdr-singleplayer.backup.viewer.loading"),
                width / 2, centre, 0xffaaaaaa);
        } else if (!store().error().isEmpty()) {
            int y = centre - 10;
            for (var line : font.split(localized(store().error()), column)) {
                if (y > centre + 14) break;
                graphics.centeredText(font, line, width / 2, y, 0xffff7777);
                y += 10;
            }
        } else if (entries().isEmpty()) {
            graphics.centeredText(font, Component.translatable("mcdr-singleplayer.backup.viewer.empty",
                Component.translatable("mcdr-singleplayer.backup.viewer.tab." + tab, 0)),
                width / 2, centre, 0xffaaaaaa);
        }

        var chosen = chosen();
        if (chosen != null) {
            Component detail = chosen.restorable()
                ? Component.translatable("mcdr-singleplayer.backup.viewer.detail", size(chosen.size()),
                    String.join(", ", chosen.dimensions()))
                : localized(chosen.reason());
            graphics.centeredText(font, font.split(detail, column).get(0), width / 2, noteY(),
                chosen.restorable() ? 0xffa0a0a0 : 0xffffcc66);
        }
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.backup.viewer.warning"),
            width / 2, warningY(), armed ? 0xffff7777 : 0xffffcc66);
        if (!error.isEmpty()) {
            int line = errorY();
            for (var part : font.split(localized(error), column)) {
                if (line > height - 10) break;
                graphics.centeredText(font, part, width / 2, line, 0xffff7777);
                line += 10;
            }
        }
        super.extractRenderState(graphics, mouseX, mouseY, ticks);
    }

    private static Component localized(String text) {
        return text.startsWith("mcdr-singleplayer.") ? Component.translatable(text) : Component.literal(text);
    }

    private static String size(long bytes) {
        if (bytes <= 0) return "0 B";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024) + " KiB";
        return String.format("%.1f MiB", bytes / (1024.0 * 1024.0));
    }

    @Override public void onClose() {
        Minecraft.getInstance().gui.setScreen(parent != null ? parent : new TitleScreen());
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
}
