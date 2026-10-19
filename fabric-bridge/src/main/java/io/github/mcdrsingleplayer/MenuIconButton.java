package io.github.mcdrsingleplayer;

import net.minecraft.ChatFormatting;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.network.chat.Component;

/**
 * The title-screen entry that opens the bridge screen: a square vanilla button carrying the mod icon
 * and the red pending-work mark the neighbouring mod buttons also use.
 *
 * <p>The icon is drawn from an embedded pixel table with {@code fill}, because that is the one
 * drawing call every declared Minecraft version shares. A bitmap font glyph never rendered, even
 * fully opaque at 32 pixels, and the textured {@code blit} overload differs between 26.x (render
 * pipeline), 1.21.11 and earlier, which no single source line satisfies. The table comes from the mod icon's own
alpha channel, so transparent cells are skipped and the coloured icon is painted straight onto
the vanilla frame.
 */
final class MenuIconButton extends Button {
    private static final int SIZE = 16;
    /** Square, so the entry matches the icon-only buttons the neighbouring mods add. */
    private static final int WIDTH = 20;
    private static final Component ATTENTION_BADGE = Component.literal("\u25cf").withStyle(ChatFormatting.RED);
    private static final int[] ICON = {
            0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xfffdd102, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xfffad103, 0xfffff003, 0xfffdd502, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xfff9d503, 0xffffdf03, 0xffffe802, 0xfffdd402, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xfffdd502, 0xffffe502, 0xffffe102, 0xfffdd401, 0x00000000,
            0xff0990fc, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xff33c444, 0xff33c547, 0xff35c747, 0xff36c444, 0x00000000, 0x00000000, 0x00000000, 0xfffdd602, 0xffffe202, 0xfffdd202,
            0xff0994ff, 0xff088bf7, 0x00000000, 0x00000000, 0x00000000, 0xff34ca4a, 0xff36d14b, 0xff30bd42, 0xff32bc43, 0xff36d14b, 0xff2dcf46, 0x00000000, 0x00000000, 0x00000000, 0xfffcd202, 0xffffd602,
            0xff088cfb, 0xff088af6, 0x00000000, 0x00000000, 0xff268a17, 0xff2ba129, 0xff33c346, 0xff34c448, 0xff2dc846, 0xff34c146, 0xff618840, 0xff87623c, 0x00000000, 0x00000000, 0xfffbcf02, 0xffffd602,
            0xff088dfb, 0xff088af6, 0x00000000, 0x00000000, 0xff288c14, 0xff24810d, 0xff248111, 0xff2baa30, 0xff5d9142, 0xff8a5739, 0xff91523a, 0xff8c5d3b, 0x00000000, 0x00000000, 0xfffbd002, 0xffffd602,
            0xff088dfb, 0xff088bf6, 0x00000000, 0x00000000, 0xff278a14, 0x00000000, 0xff258512, 0xff247e0f, 0xff91503b, 0x00000000, 0x00000000, 0xff865b38, 0x00000000, 0x00000000, 0xfffbd003, 0xffffd602,
            0xff088dfb, 0xff088bf5, 0x00000000, 0x00000000, 0xff258414, 0x00000000, 0xff248413, 0xff288315, 0xff8b5b3d, 0x00000000, 0x00000000, 0xff875a39, 0x00000000, 0x00000000, 0xfffbd003, 0xffffd502,
            0xff0991ff, 0xff088df9, 0x00000000, 0x00000000, 0xff278712, 0xff268516, 0xff268a14, 0xff278213, 0xff8b593c, 0xff895e39, 0xff875a3a, 0xff875c3a, 0x00000000, 0x00000000, 0xfffdd102, 0xffffe502,
            0xff088af7, 0xff0996ff, 0xff088ffa, 0x00000000, 0x00000000, 0x00000000, 0xff278a15, 0xff278216, 0xff8a5a3b, 0xff8a5e3c, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0xff088efa, 0xff0a9fff, 0xff098ff8, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0x00000000, 0xff098df9, 0xff098efa, 0xff0a9eff, 0xff098ef8, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xff098dfa, 0xff0a9aff, 0xff088bf7, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
            0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0xff098cf7, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
    };

    private boolean needsAttention;

    MenuIconButton(int x, int y, int height, OnPress onPress) {
        super(x, y, WIDTH, height, Component.empty(), onPress, DEFAULT_NARRATION);
        setTooltip(Tooltip.create(Component.translatable("mcdr-singleplayer.setup.button")));
    }

    /** Only 26.x requires this; scripts/generate_compat.py rewrites it for the other API shapes. */
    @Override
    protected void extractContents(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        extractDefaultSprite(graphics);
        drawIcon(graphics, getX() + (getWidth() - SIZE) / 2, getY() + (getHeight() - SIZE) / 2);
    }

    /** The one drawing call every version shares, so no per-version rewrite is needed here. */
    private static void drawIcon(GuiGraphicsExtractor graphics, int left, int top) {
        for (int row = 0; row < SIZE; row++) {
            for (int column = 0; column < SIZE; column++) {
                int color = ICON[row * SIZE + column];
                if (color == 0) continue;
                graphics.fill(left + column, top + row, left + column + 1, top + row + 1, color);
            }
        }
    }

    /** The setup state can change while the menu is open, so the mark follows it. */
    void refresh() {
        boolean attention = SingleplayerBridge.setupNeedsAttention();
        if (attention == needsAttention) return;
        needsAttention = attention;
        setMessage(attention ? Component.empty().append(ATTENTION_BADGE) : Component.empty());
    }
}
