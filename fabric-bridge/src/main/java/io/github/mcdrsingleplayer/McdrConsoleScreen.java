package io.github.mcdrsingleplayer;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/**
 * The running MCDR console: the newest output lines plus a line to send a command.
 *
 * The controller mirrors the child's console into a small file, so this screen only ever reads it;
 * nothing here can block a running backup or restore.
 */
final class McdrConsoleScreen extends Screen {
    interface Behaviour {
        List<String> lines(int limit);
        void send(String command);
    }

    private static final int REFRESH_MILLIS = 500;
    private static final int LINE_HEIGHT = 10;

    private final Behaviour behaviour;
    private final List<String> lines = new ArrayList<>();
    private EditBox input;
    private long fetchedAt;

    McdrConsoleScreen(Behaviour behaviour) {
        super(Component.translatable("mcdr-singleplayer.console.title"));
        this.behaviour = behaviour;
    }

    @Override
    protected void init() {
        // UI_POLISH_2026
        int inputWidth = panelWidth() - 24;
        int left = panelX() + 12;
        int half = inputWidth / 2 - 2;
        input = new EditBox(font, left, height - 58, inputWidth, 20,
                Component.translatable("mcdr-singleplayer.console.input"));
        input.setMaxLength(256);
        addRenderableWidget(input);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.console.send"),
                button -> submit()).bounds(left, height - 34, half, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.setup.close"),
                button -> onClose()).bounds(left + half + 4, height - 34, half, 20).build());
    }

    // UI_POLISH_2026
    private int panelWidth() { return Math.min(760, Math.max(240, width - 20)); }
    private int panelX() { return (width - panelWidth()) / 2; }
    private int logTop() { return 42; }
    private int logBottom() { return Math.max(logTop() + LINE_HEIGHT + 8, height - 84); }

    private void submit() {
        String command = input == null ? "" : input.getValue().trim();
        if (command.isEmpty()) return;
        behaviour.send(command);
        input.setValue("");
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        // UI_POLISH_2026
        refresh();
        int panelX = panelX();
        int panelWidth = panelWidth();
        VanillaConfluxUi.backdrop(graphics, width, height, 0xb0000000);
        VanillaConfluxUi.panel(graphics, panelX, 12, panelWidth, height - 24);
        VanillaConfluxUi.accent(graphics, panelX, 12, panelWidth);
        VanillaConfluxUi.center(graphics, font, title, width / 2, 20, 0xffffffff);
        VanillaConfluxUi.divider(graphics, panelX + 12, 36, panelWidth - 24);

        int logX = panelX + 12;
        int logWidth = panelWidth - 24;
        int logTop = logTop();
        int logBottom = logBottom();
        VanillaConfluxUi.panel(graphics, logX, logTop, logWidth, logBottom - logTop);
        int capacity = Math.max(1, (logBottom - logTop - 14) / LINE_HEIGHT);
        List<String> shown = window(capacity);
        if (shown.isEmpty()) {
            VanillaConfluxUi.center(graphics, font,
                    Component.translatable("mcdr-singleplayer.console.empty"),
                    width / 2, (logTop + logBottom) / 2, 0xff888888);
        } else {
            int startY = Math.max(logTop + 6, logBottom - 8 - shown.size() * LINE_HEIGHT);
            for (int index = 0; index < shown.size(); index++) {
                String line = fit(shown.get(index), logWidth - 16);
                VanillaConfluxUi.left(graphics, font, line, logX + 8,
                        startY + index * LINE_HEIGHT, lineColor(line));
            }
        }

        VanillaConfluxUi.center(graphics, font,
                Component.translatable("mcdr-singleplayer.console.hint"),
                width / 2, height - 76, 0xff888888);
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    /**
     * 按像素宽度截断一行，超出部分用省略号。
     *
     * 原来逐字符回退，每帧每行都要重算多次 font.width；日志行很长时是 O(n²)。
     * 这里改成二分找最长可容纳的前缀，仍是 O(log n) 次测量。
     */
    private String fit(String text, int maxWidth) {
        String value = text == null ? "" : text;
        if (font.width(value) <= maxWidth) return value;
        int low = 0;
        int high = value.length();
        while (low < high) {
            int middle = (low + high + 1) / 2;
            if (font.width(value.substring(0, middle) + "…") <= maxWidth) low = middle;
            else high = middle - 1;
        }
        return value.substring(0, low) + "…";
    }

    private static int lineColor(String text) {
        String upper = text.toUpperCase(java.util.Locale.ROOT);
        if (upper.contains("ERROR") || upper.contains("FAILED")) return 0xffff7777;
        if (upper.contains("WARN")) return 0xffffd866;
        if (upper.contains("DEBUG")) return 0xff888888;
        return 0xffcccccc;
    }

    /** Newest {@code capacity} lines; the console follows the tail. */
    private List<String> window(int capacity) {
        if (lines.isEmpty()) return List.of();
        int start = Math.max(0, lines.size() - capacity);
        return lines.subList(start, lines.size());
    }

    private void refresh() {
        long now = System.currentTimeMillis();
        if (now - fetchedAt < REFRESH_MILLIS && !lines.isEmpty()) return;
        fetchedAt = now;
        List<String> fresh = behaviour.lines(400);
        lines.clear();
        lines.addAll(fresh);
    }

    /** Long lines are cut so one message cannot push the rest off screen. */
    private String fit(String text) {
        int limit = Math.max(20, (width - 24) / 6);
        return text.length() <= limit ? text : text.substring(0, limit - 1) + '…';
    }

    @Override public boolean isPauseScreen() { return false; }
    @Override public boolean shouldCloseOnEsc() { return true; }
}
