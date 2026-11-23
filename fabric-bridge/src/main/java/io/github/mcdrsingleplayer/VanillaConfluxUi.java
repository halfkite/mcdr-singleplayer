package io.github.mcdrsingleplayer;

import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.network.chat.Component;
import net.minecraft.util.FormattedCharSequence;

/**
 * Minecraft 原版像素界面的轻量面板绘制工具。
 * 直角、细边框和中性灰层次参考 Conflux Map，不替换原版按钮与输入框。
 */
final class VanillaConfluxUi {
    private static final int BORDER = 0xff555555;
    private static final int PANEL = 0xe0101010;
    private static final int TOP_EDGE = 0xff888888;
    private static final int BOTTOM_EDGE = 0xff242424;
    private static final int ACCENT = 0xffc6c6c6;
    private static final int DIVIDER = 0xff444444;

    private VanillaConfluxUi() { }

    static void backdrop(GuiGraphicsExtractor graphics, int width, int height, int color) {
        graphics.fill(0, 0, width, height, color);
    }

    static void panel(GuiGraphicsExtractor graphics, int x, int y, int width, int height) {
        if (width < 4 || height < 4) return;
        graphics.fill(x, y, x + width, y + height, BORDER);
        graphics.fill(x + 1, y + 1, x + width - 1, y + height - 1, PANEL);
        graphics.fill(x + 1, y + 1, x + width - 1, y + 2, TOP_EDGE);
        graphics.fill(x + 1, y + height - 2, x + width - 1, y + height - 1, BOTTOM_EDGE);
    }

    static void accent(GuiGraphicsExtractor graphics, int x, int y, int width) {
        if (width > 2) graphics.fill(x + 1, y + 1, x + width - 1, y + 3, ACCENT);
    }

    static void divider(GuiGraphicsExtractor graphics, int x, int y, int width) {
        if (width > 0) graphics.fill(x, y, x + width, y + 1, DIVIDER);
    }

    static void center(GuiGraphicsExtractor graphics, Font font, Component text,
            int centerX, int y, int color) {
        graphics.centeredText(font, text, centerX, y, color);
    }

    /** 换行后的每一行是 FormattedCharSequence，不是 Component，单独接一个重载。 */
    static void center(GuiGraphicsExtractor graphics, Font font, FormattedCharSequence text,
            int centerX, int y, int color) {
        graphics.centeredText(font, text, centerX, y, color);
    }

    /** 纯文本版：先按像素宽度算好居中位置，再交给组件绘制。 */
    static void center(GuiGraphicsExtractor graphics, Font font, String text,
            int centerX, int y, int color) {
        String value = text == null ? "" : text;
        graphics.centeredText(font, Component.literal(value), centerX, y, color);
    }

    static void left(GuiGraphicsExtractor graphics, Font font, String text,
            int x, int y, int color) {
        String value = text == null ? "" : text;
        graphics.centeredText(font, Component.literal(value), x + font.width(value) / 2, y, color);
    }

    static void left(GuiGraphicsExtractor graphics, Font font, FormattedCharSequence text,
            int x, int y, int color) {
        graphics.centeredText(font, text, x + font.width(text) / 2, y, color);
    }
}
