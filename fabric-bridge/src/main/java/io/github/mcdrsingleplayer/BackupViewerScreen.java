package io.github.mcdrsingleplayer;

import java.util.List;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.network.chat.Component;

/**
 * 适用于 Minecraft 26.3 的原版风格存档备份管理面板。
 *
 * 仅负责展示目录快照和派发操作；读取、创建、恢复仍交给 BackupCatalogClient。
 * 参考 Conflux Map 的中性灰直角边框与紧凑信息层级，保留原生按钮交互。
 * 根据窗口尺寸自动切换双栏/单栏，避免长备注或错误消息覆盖操作按钮。
 */
public final class BackupViewerScreen extends Screen {
    private static final int PANEL_MAX_WIDTH = 760;
    private static final int ROW_HEIGHT = 26;
    private static final int ROW_STEP = 31;
    private static final int MAX_ROWS = 7;
    private static final int PANEL = 0xf0181818;
    private static final int BORDER = 0xff6b6b6b;
    private static final int SECTION = 0xe0191919;
    private static final int ACCENT = 0xffe4e4e4;
    private static final int MUTED = 0xffaaaaaa;
    private static final int ERROR = 0xffff7777;
    private static final int WARNING = 0xffe4c883;
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

    /** 编辑世界界面的入口；切换到恢复流程前由原版编辑界面释放存档锁。 */
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

    /** 屏幕自适应布局：没有侧栏的窄窗口保留完整的选择、翻页和操作流程。 */
    private int panelWidth() { return Math.max(160, Math.min(PANEL_MAX_WIDTH, width - 16)); }
    private int panelHeight() { return Math.max(190, Math.min(450, height - 14)); }
    private int panelX() { return (width - panelWidth()) / 2; }
    private int panelY() { return Math.max(4, (height - panelHeight()) / 2); }
    private int panelBottom() { return panelY() + panelHeight(); }
    private int contentX() { return panelX() + 12; }
    private int contentWidth() { return panelWidth() - 24; }
    private boolean split() { return panelWidth() >= 600 && panelHeight() >= 315; }
    private boolean compact() { return panelHeight() < 315; }
    private boolean tiny() { return panelHeight() < 240; }
    private int listWidth() { return split() ? (contentWidth() * 55 / 100) - 6 : contentWidth(); }
    private int detailX() { return contentX() + listWidth() + 12; }
    private int detailWidth() { return contentWidth() - listWidth() - 12; }
    private int tabsY() { return panelY() + (tiny() ? 27 : compact() ? 37 : 47); }
    private int sectionY() { return tabsY() + (tiny() ? 23 : 27); }
    private int listY() { return sectionY() + (tiny() ? 12 : 16); }
    private int footerY() { return panelBottom() - (tiny() ? 27 : 30); }
    private int toolsY() { return footerY() - (tiny() ? 24 : 29); }
    private int statusY() { return toolsY() - (tiny() ? 12 : 16); }
    private int pagerY() { return statusY() - (tiny() ? 24 : 27); }
    private int rows() {
        int reserved = split() || tiny() ? 0 : 27;
        return Math.max(1, Math.min(MAX_ROWS, (pagerY() - listY() - reserved - 4) / ROW_STEP));
    }
    private int safePage() {
        if (catalog == null || entries().isEmpty()) return 0;
        return Math.min(Math.max(page, 0), (entries().size() - 1) / rows());
    }

    @Override protected void init() {
        int x = contentX();
        int tabWidth = (contentWidth() - 8) / TABS.length;
        for (int index = 0; index < TABS.length; index++) {
            String kind = TABS[index];
            var button = addRenderableWidget(Button.builder(tab(kind), pressed -> switchStore(kind))
                .bounds(x + index * (tabWidth + 4), tabsY(), tabWidth, 20).build());
            button.active = catalog != null && !working && !tab.equals(kind);
        }

        if (catalog == null) {
            if (!loading) {
                loading = true;
                BackupCatalogClient.load(world, result -> {
                    if (Minecraft.getInstance().gui.screen() == this)
                        Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, result, error,
                            tab, 0, "", false));
                });
            }
        } else {
            int actualPage = safePage();
            int from = actualPage * rows();
            int to = Math.min(entries().size(), from + rows());
            for (int index = from; index < to; index++) {
                BackupCatalogClient.Entry entry = entries().get(index);
                int y = listY() + (index - from) * ROW_STEP;
                var item = addRenderableWidget(Button.builder(Component.literal(rowLabel(entry)), pressed ->
                    Minecraft.getInstance().gui.setScreen(with(tab, actualPage, entry.ref(), false)))
                    .bounds(x, y, listWidth(), ROW_HEIGHT).build());
                item.active = !working;
            }
            var previous = addRenderableWidget(Button.builder(Component.literal("<"), pressed ->
                Minecraft.getInstance().gui.setScreen(with(tab, actualPage - 1, selected, false)))
                .bounds(x, pagerY(), 28, 20).build());
            previous.active = actualPage > 0 && !working;
            var next = addRenderableWidget(Button.builder(Component.literal(">"), pressed ->
                Minecraft.getInstance().gui.setScreen(with(tab, actualPage + 1, selected, false)))
                .bounds(x + listWidth() - 28, pagerY(), 28, 20).build());
            next.active = (actualPage + 1) * rows() < entries().size() && !working;

            int half = (contentWidth() - 6) / 2;
            boolean configured = store().error().isEmpty();
            boolean requiresSetup = !tab.equals("vanilla") && !configured;
            var make = addRenderableWidget(Button.builder(
                Component.translatable(requiresSetup ? "mcdr-singleplayer.backup.viewer.create_config"
                    : "mcdr-singleplayer.backup.viewer.make_backup." + tab),
                pressed -> { if (requiresSetup) createConfig(); else makeBackup(); })
                .bounds(x, toolsY(), half, 20).build());
            make.active = !working && (configured || requiresSetup);
            var folder = addRenderableWidget(Button.builder(
                Component.translatable("mcdr-singleplayer.backup.viewer.open_folder"),
                pressed -> openFolder()).bounds(x + half + 6, toolsY(), contentWidth() - half - 6, 20).build());
            folder.active = !working;
        }

        int backWidth = Math.min(104, Math.max(55, contentWidth() / 3));
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.back"),
            pressed -> onClose()).bounds(x, footerY(), backWidth, 20).build());
        var selection = chosen();
        var confirm = addRenderableWidget(Button.builder(Component.translatable(
            armed ? "mcdr-singleplayer.backup.viewer.confirm_armed"
                : "mcdr-singleplayer.backup.viewer.confirm"), pressed -> restore())
            .bounds(x + backWidth + 6, footerY(), contentWidth() - backWidth - 6, 20).build());
        confirm.active = selection != null && selection.restorable() && error.isEmpty() && !working;
    }

    private Component tab(String kind) {
        return Component.translatable("mcdr-singleplayer.backup.viewer.tab." + kind, count(kind));
    }

    /**
     * 滚轮翻页：在列表区域滚动时走上一页/下一页。
     *
     * 只认列表所在的那一块，避免在标签页或按钮上滚动时页面自己跳走。界面靠翻页
     * 而不是连续滚动，所以一次滚轮手势只移动一页，和点 `<` `>` 等价。
     */
    @Override public boolean mouseScrolled(double mouseX, double mouseY, double horizontal, double vertical) {
        if (!listRegionContains(mouseX, mouseY) || working) return super.mouseScrolled(mouseX, mouseY, horizontal, vertical);
        if (vertical > 0) movePage(-1);
        else if (vertical < 0) movePage(1);
        return true;
    }

    /** 滚轮是否落在列表区域内（列表列 + 分页行之间）。 */
    private boolean listRegionContains(double x, double y) {
        if (catalog == null) return false;
        int left = contentX();
        int right = left + listWidth();
        int top = listY() - 4;
        int bottom = pagerY() + 20;
        return x >= left && x <= right && y >= top && y <= bottom;
    }

    /** 翻页；越界时什么也不做，不把页码推成负数或超出末页。 */
    private void movePage(int delta) {
        int target = safePage() + delta;
        if (target < 0) return;
        if (target * rows() >= entries().size()) return;
        Minecraft.getInstance().gui.setScreen(with(tab, target, selected, false));
    }

    /**
     * 键盘选择：上下键在列表里移动选中项，左右键翻页，回车回档。
     *
     * 选中项存在 {@link #selected} 里，移动后整页重建（和点击行一致），这样详情面板
     * 与确认按钮的可用状态都跟着刷新。Tab/Enter 仍然交给原版按钮导航，不受影响。
     *
     * 26.3 起原版把按键改成了 KeyEvent 事件对象，不再传 (keyCode, scanCode, modifiers)，
     * 所以这里从事件里取键码。
     */
    @Override public boolean keyPressed(KeyEvent event) {
        if (!working) {
            switch (event.key()) {
                case 265 -> { moveSelection(-1); return true; }   // GLFW_KEY_UP
                case 264 -> { moveSelection(1); return true; }    // GLFW_KEY_DOWN
                case 263 -> { movePage(-1); return true; }        // GLFW_KEY_LEFT
                case 262 -> { movePage(1); return true; }         // GLFW_KEY_RIGHT
                case 257 -> {                                      // GLFW_KEY_ENTER
                    if (chosen() != null) { restore(); return true; }
                }
                default -> { }
            }
        }
        return super.keyPressed(event);
    }

    /**
     * 移动选中项；跨页时自动翻到相邻页。
     *
     * 没有选中项时，向下选第一条、向上选最后一条，避免按键完全没反应。
     */
    private void moveSelection(int delta) {
        if (catalog == null) return;
        var items = entries();
        if (items.isEmpty()) return;
        int index = -1;
        for (int position = 0; position < items.size(); position++) {
            if (items.get(position).ref().equals(selected)) { index = position; break; }
        }
        if (index < 0) index = delta > 0 ? -1 : items.size();
        index += delta;
        if (index < 0) index = 0;
        if (index >= items.size()) index = items.size() - 1;
        String next = items.get(index).ref();
        // 目标项可能在别的页上，页码跟着选中项走。
        Minecraft.getInstance().gui.setScreen(with(tab, index / rows(), next, false));
    }

    private int count(String kind) {
        if (catalog == null) return 0;
        return switch (kind) {
            case "chunk" -> catalog.chunk().entries().size();
            case "vanilla" -> catalog.vanilla().entries().size();
            default -> catalog.prime().entries().size();
        };
    }

    private String rowLabel(BackupCatalogClient.Entry entry) {
        String date = entry.date().isBlank() ? entry.ref() : entry.date();
        String comment = entry.comment().isBlank() ? "" : "  ·  " + entry.comment();
        String symbol = entry.ref().equals(selected) ? "> " : "  ";
        return fit(symbol + date + comment, listWidth() - 22);
    }

    private void switchStore(String nextTab) {
        if (catalog == null || working) return;
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
        BackupViewerScreen pending = with(tab, safePage(), selected, false);
        pending.working = true;
        Minecraft.getInstance().gui.setScreen(pending);
        BackupCatalogClient.setup(world, tab.equals("chunk"), failure -> {
            if (Minecraft.getInstance().gui.screen() != pending) return;
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent,
                failure.isEmpty() ? null : catalog, failure, tab, 0, "", false));
        });
    }

    private void makeBackup() {
        if (working || catalog == null || !store().error().isEmpty()) return;
        if (tab.equals("vanilla")) {
            runCreate("", null, "");
            return;
        }
        if (tab.equals("chunk")) {
            ChunkBackupScreen.open(this, dimensions(), (dimension, region, comment) -> {
                if (dimension != null) runCreate(comment, dimension, region == null ? "" : join(region));
            });
            return;
        }
        BackupCommentScreen.open(this, "mcdr-singleplayer.backup.viewer.make_backup.prime",
            comment -> { if (comment != null) runCreate(comment, null, ""); });
    }

    private static String join(int[] region) {
        return region[0] + "," + region[1] + "," + region[2] + "," + region[3];
    }

    private List<String> dimensions() {
        var selection = chosen();
        if (selection != null && !selection.dimensions().isEmpty()) return selection.dimensions();
        return List.of("minecraft:overworld", "minecraft:the_nether", "minecraft:the_end");
    }

    private void runCreate(String comment, String dimension, String region) {
        int[] bounds = null;
        if (region != null && !region.isEmpty()) {
            String[] parts = region.split(",");
            bounds = new int[parts.length];
            for (int i = 0; i < parts.length; i++) bounds[i] = Integer.parseInt(parts[i]);
        }
        // 新界面继承处理中状态，避免创建期间误以为按钮失效或可以再次点击。
        BackupViewerScreen pending = with(tab, safePage(), selected, false);
        pending.working = true;
        Minecraft.getInstance().gui.setScreen(pending);
        java.util.function.Consumer<String> done = failure -> {
            if (Minecraft.getInstance().gui.screen() != pending) return;
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent,
                failure.isEmpty() ? null : catalog, failure, tab, 0, "", false));
        };
        if (tab.equals("vanilla")) {
            BackupCatalogClient.createVanilla(world, done);
        } else {
            BackupCatalogClient.create(world, tab.equals("chunk"), comment == null ? "" : comment,
                dimension, bounds, done);
        }
    }

    private void openFolder() {
        if (working) return;
        BackupCatalogClient.open(world, tab, failure -> {
            if (failure.isEmpty() || Minecraft.getInstance().gui.screen() != this) return;
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, catalog, failure,
                tab, safePage(), selected, false));
        });
    }

    private void restore() {
        var selection = chosen();
        if (catalog == null || selection == null || !selection.restorable() || !error.isEmpty() || working) return;
        if (RestoreProgressMonitor.blocks(world)) {
            Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, parent, catalog,
                "mcdr-singleplayer.backup.viewer.busy", tab, safePage(), selected, false));
            return;
        }
        if (!armed) {
            Minecraft.getInstance().gui.setScreen(with(tab, safePage(), selected, true));
            return;
        }
        if (parent instanceof net.minecraft.client.gui.screens.worldselection.EditWorldScreen) parent.onClose();
        Minecraft.getInstance().gui.setScreen(new TitleScreen());
        BackupCatalogClient.restore(world, selection.ref(), reason -> {
            if (Minecraft.getInstance().gui.screen() instanceof TitleScreen)
                Minecraft.getInstance().gui.setScreen(new BackupViewerScreen(world, null, null, reason,
                    "prime", 0, "", false));
        });
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float ticks) {
        graphics.fill(0, 0, width, height, 0xc9000000);
        box(graphics, panelX(), panelY(), panelWidth(), panelHeight(), PANEL, BORDER);
        graphics.fill(panelX() + 1, panelY() + 1, panelX() + panelWidth() - 1, panelY() + 4, ACCENT);
        graphics.centeredText(font, title, width / 2, panelY() + 11, 0xffffffff);
        if (!tiny())
            drawLeft(graphics, fit(world, contentWidth() - 6), contentX(), panelY() + 25, MUTED);
        if (!compact()) {
            graphics.fill(contentX(), tabsY() - 7, contentX() + contentWidth(), tabsY() - 6, BORDER);
        }
        if (catalog != null) {
            String heading = tr("section.list", entries().size());
            drawLeft(graphics, heading, contentX(), sectionY(), 0xffe6e6e6);
            if (split()) {
                box(graphics, detailX(), listY() - 3, detailWidth(), pagerY() - listY() + 25,
                    SECTION, BORDER);
                drawDetails(graphics, chosen());
            } else if (!tiny()) {
                drawCompactDetails(graphics, chosen());
            }
            int pages = Math.max(1, (entries().size() + rows() - 1) / rows());
            graphics.centeredText(font, Component.translatable(
                "mcdr-singleplayer.backup.viewer.page", safePage() + 1, pages),
                contentX() + listWidth() / 2, pagerY() + 6, MUTED);
        }

        int center = listY() + Math.max(0, pagerY() - listY()) / 2;
        if (catalog == null) {
            graphics.centeredText(font, Component.translatable("mcdr-singleplayer.backup.viewer.loading"),
                contentX() + listWidth() / 2, center, MUTED);
        } else if (!store().error().isEmpty()) {
            centeredLines(graphics, localized(store().error()), contentX() + listWidth() / 2,
                center - 10, listWidth() - 12, 3, ERROR);
        } else if (entries().isEmpty()) {
            centeredLines(graphics, Component.translatable("mcdr-singleplayer.backup.viewer.empty",
                Component.translatable("mcdr-singleplayer.backup.viewer.tab." + tab, 0)),
                contentX() + listWidth() / 2, center, listWidth() - 12, 3, MUTED);
        }

        String message = working ? tr("progress") : !error.isEmpty() ? localized(error).getString()
            : armed ? tr("confirm_armed") : tr("warning");
        int color = !error.isEmpty() ? ERROR : working || armed ? WARNING : MUTED;
        graphics.centeredText(font, Component.literal(fit(message, contentWidth() - 8)),
            width / 2, statusY(), color);
        super.extractRenderState(graphics, mouseX, mouseY, ticks);
        // 原版按钮之上叠加轻量状态线，保留键盘、旁白和手柄的原生可访问交互。
        int underlineWidth = (contentWidth() - 8) / TABS.length;
        for (int index = 0; index < TABS.length; index++) {
            if (!tab.equals(TABS[index])) continue;
            int x = contentX() + index * (underlineWidth + 4);
            graphics.fill(x + 3, tabsY() + 19, x + underlineWidth - 3, tabsY() + 21, ACCENT);
        }
        if (catalog != null) {
            int from = safePage() * rows();
            int to = Math.min(entries().size(), from + rows());
            for (int i = from; i < to; i++) {
                var entry = entries().get(i);
                if (!entry.ref().equals(selected)) continue;
                int y = listY() + (i - from) * ROW_STEP;
                graphics.fill(contentX() + 2, y + 3, contentX() + 5, y + ROW_HEIGHT - 3, ACCENT);
            }
        }
    }

    private void drawDetails(GuiGraphicsExtractor graphics, BackupCatalogClient.Entry selection) {
        int x = detailX() + 12;
        int limit = detailWidth() - 24;
        int y = listY() + 9;
        drawLeft(graphics, tr("section.details"), x, y, ACCENT);
        y += 21;
        if (selection == null) {
            drawLeft(graphics, fit(tr("detail.none"), limit), x, y + 10, MUTED);
            return;
        }
        y = detailField(graphics, x, y, limit, "field.date", selection.date(), pagerY());
        y = detailField(graphics, x, y, limit, "field.size", size(selection.size()), pagerY());
        y = detailField(graphics, x, y, limit, "field.operator", selection.operator(), pagerY());
        y = detailField(graphics, x, y, limit, "field.dimensions",
            String.join(", ", selection.dimensions()), pagerY());
        y = detailField(graphics, x, y, limit, "field.comment", selection.comment(), pagerY());
        if (y + 11 <= pagerY()) {
            String status = selection.restorable() ? tr("state.ready") : selection.reason().isBlank()
                ? tr("state.unavailable") : localized(selection.reason()).getString();
            drawLeft(graphics, fit(tr("field.status") + "  " + status, limit), x, y,
                selection.restorable() ? ACCENT : WARNING);
        }
        if (selection.safety() && y + 24 <= pagerY())
            drawLeft(graphics, tr("state.temporary"), x, y + 14, WARNING);
    }

    private int detailField(GuiGraphicsExtractor graphics, int x, int y, int limit, String key,
            String value, int bottom) {
        if (y + 13 > bottom) return y;
        String shown = value == null || value.isBlank() ? tr("detail.unknown") : value;
        drawLeft(graphics, fit(tr(key) + "  " + shown, limit), x, y, 0xffdedede);
        return y + 24;
    }

    private void drawCompactDetails(GuiGraphicsExtractor graphics, BackupCatalogClient.Entry selection) {
        if (selection == null) return;
        int y = pagerY() - 23;
        String details = selection.restorable()
            ? tr("field.size") + " " + size(selection.size()) + "  ·  " + selection.comment()
            : localized(selection.reason()).getString();
        box(graphics, contentX(), y - 3, contentWidth(), 18, SECTION, BORDER);
        drawLeft(graphics, fit(details, contentWidth() - 12), contentX() + 6, y + 2,
            selection.restorable() ? MUTED : WARNING);
    }

    private void box(GuiGraphicsExtractor graphics, int x, int y, int w, int h, int background, int border) {
        graphics.fill(x, y, x + w, y + h, border);
        graphics.fill(x + 1, y + 1, x + w - 1, y + h - 1, background);
    }

    private void drawLeft(GuiGraphicsExtractor graphics, String value, int x, int y, int color) {
        graphics.centeredText(font, Component.literal(value), x + font.width(value) / 2, y, color);
    }

    private void centeredLines(GuiGraphicsExtractor graphics, Component message, int centerX,
            int startY, int limit, int maxLines, int color) {
        int row = 0;
        for (var line : font.split(message, Math.max(35, limit))) {
            if (row >= maxLines) break;
            graphics.centeredText(font, line, centerX, startY + row * 11, color);
            row++;
        }
    }

    private String fit(String input, int maxWidth) {
        String value = input == null ? "" : input;
        int limit = Math.max(12, maxWidth);
        if (font.width(value) <= limit) return value;
        while (value.length() > 1 && font.width(value + "…") > limit)
            value = value.substring(0, value.length() - 1);
        return value + "…";
    }

    private static Component localized(String value) {
        return value.startsWith("mcdr-singleplayer.") ? Component.translatable(value)
            : Component.literal(value);
    }

    private static String tr(String suffix, Object... args) {
        return Component.translatable("mcdr-singleplayer.backup.viewer." + suffix, args).getString();
    }

    private static String size(long bytes) {
        if (bytes <= 0) return "0 B";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024L * 1024) return bytes / 1024 + " KiB";
        if (bytes < 1024L * 1024 * 1024) return String.format("%.1f MiB", bytes / (1024.0 * 1024));
        return String.format("%.1f GiB", bytes / (1024.0 * 1024 * 1024));
    }

    @Override public void onClose() {
        Minecraft.getInstance().gui.setScreen(parent != null ? parent : new TitleScreen());
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
}
