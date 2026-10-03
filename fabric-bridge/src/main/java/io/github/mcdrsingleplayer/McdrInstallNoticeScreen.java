package io.github.mcdrsingleplayer;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Explains the MCDR setup that starts after Python is detected. */
final class McdrInstallNoticeScreen extends Screen {
    private final boolean autoInstall;
    private final Runnable onDismiss;

    McdrInstallNoticeScreen(boolean autoInstall, Runnable onDismiss) {
        super(Component.translatable(autoInstall
                ? "mcdr-singleplayer.python.mcdr_install_title"
                : "mcdr-singleplayer.python.mcdr_ready_title"));
        this.autoInstall = autoInstall;
        this.onDismiss = onDismiss;
    }

    @Override
    protected void init() {
        int panelWidth = Math.min(400, width - 24);
        int panelLeft = (width - panelWidth) / 2;
        int textWidth = Math.min(360, width - 40);
        int messageLines = font.split(Component.translatable(autoInstall
                ? "mcdr-singleplayer.python.mcdr_install_intro"
                : "mcdr-singleplayer.python.mcdr_ready_intro"), textWidth).size();
        int top = Math.max(20, (height - (68 + messageLines * 10)) / 2);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.python.close"), button -> onClose())
                .bounds(panelLeft + panelWidth - 78, top - 6, 68, 20).build());
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        int panelWidth = Math.min(400, width - 24);
        int panelLeft = (width - panelWidth) / 2;
        int textWidth = Math.min(360, width - 40);
        var message = font.split(Component.translatable(autoInstall
                ? "mcdr-singleplayer.python.mcdr_install_intro"
                : "mcdr-singleplayer.python.mcdr_ready_intro"), textWidth);
        int contentHeight = 68 + message.size() * 10;
        int top = Math.max(20, (height - contentHeight) / 2);
        int panelBottom = Math.min(height - 12, top + contentHeight);
        graphics.fill(0, 0, width, height, 0x90000000);
        graphics.fill(panelLeft, top - 8, panelLeft + panelWidth, panelBottom + 8, 0xd0101010);
        graphics.fill(panelLeft, top - 8, panelLeft + panelWidth, top - 7, 0xff555555);
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.mod_name"), width / 2, top - 2, 0xffaaaaaa);
        graphics.centeredText(font, title, width / 2, top + 20, 0xffffffff);
        int y = top + 46;
        for (var line : message) {
            graphics.centeredText(font, line, width / 2, y, 0xffdddddd);
            y += 10;
        }
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.python.escape_hint"), width / 2, y + 8, 0xff888888);
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    @Override public void onClose() {
        super.onClose();
        onDismiss.run();
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
    @Override public boolean isPauseScreen() { return true; }
}
