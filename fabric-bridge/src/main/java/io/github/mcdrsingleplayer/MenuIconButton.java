package io.github.mcdrsingleplayer;

import net.minecraft.ChatFormatting;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.renderer.RenderPipelines;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;

/**
 * Title-screen entry drawn like the Flashback and Mod Menu buttons: the vanilla button frame with
 * the mod icon blitted on top, plus the red pending-work mark those mods also use. The icon is a
 * real texture, so no font pack can remap or hide it.
 */
final class MenuIconButton extends Button {
    private static final Identifier ICON = Identifier.parse("mcdr-singleplayer:textures/gui/icon.png");
    private static final Component ATTENTION_BADGE = Component.literal("\u25cf").withStyle(ChatFormatting.RED);
    private static final int ICON_SIZE = 16;

    private boolean needsAttention;

    MenuIconButton(int x, int y, int width, int height, OnPress onPress) {
        super(x, y, width, height, Component.translatable("mcdr-singleplayer.setup.button"), onPress,
                DEFAULT_NARRATION);
        setTooltip(Tooltip.create(getMessage()));
    }

    @Override
    protected void extractContents(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        extractDefaultSprite(graphics);
        int iconX = getX() + (getWidth() - ICON_SIZE) / 2;
        int iconY = getY() + (getHeight() - ICON_SIZE) / 2;
        graphics.blit(RenderPipelines.GUI_TEXTURED, ICON, iconX, iconY, 0.0f, 0.0f, ICON_SIZE, ICON_SIZE,
                ICON_SIZE, ICON_SIZE, 0xffffffff);
    }

    /** The setup state can change while the menu is open, so the mark follows it. */
    void refresh() {
        boolean attention = SingleplayerBridge.setupNeedsAttention();
        if (attention == needsAttention) return;
        needsAttention = attention;
        setMessage(attention
                ? Component.translatable("mcdr-singleplayer.setup.button").copy().append(ATTENTION_BADGE)
                : Component.translatable("mcdr-singleplayer.setup.button"));
    }
}
