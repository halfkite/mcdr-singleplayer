package io.github.mcdrsingleplayer;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import java.util.function.Supplier;
import net.minecraft.client.gui.screens.LoadingDotsText;

/** Dismissible installer progress; closing the screen never cancels the background process. */
final class McdrInstallNoticeScreen extends Screen {
    private final Supplier<InstallProgress> progress;
    private final Runnable onDismiss;

    McdrInstallNoticeScreen(Supplier<InstallProgress> progress, Runnable onDismiss) {
        super(Component.translatable("mcdr-singleplayer.install.title"));
        this.progress = progress;
        this.onDismiss = onDismiss;
    }

    @Override
    protected void init() {
        int buttonWidth = Math.min(200, width - 40);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.python.close"), button -> onClose())
                .bounds((width - buttonWidth) / 2, height - 32, buttonWidth, 20).build());
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        // LoadingOverlay also draws the underlying screen during language/resource reloads.
        // A translucent backdrop avoids requesting a second blur in the same frame.
        graphics.fill(0, 0, width, height, 0x90000000);
        InstallProgress value = progress.get();
        int textWidth = Math.min(360, width - 40);
        var message = font.split(Component.translatable(value.stage().equals("failed")
                ? "mcdr-singleplayer.install.failed_intro" : value.stage().equals("ready")
                ? "mcdr-singleplayer.install.ready_intro" : "mcdr-singleplayer.install.intro"), textWidth);
        Component stage = Component.translatable(value.translationKey());
        if (value.attempt() > 0) stage = stage.copy().append(Component.translatable("mcdr-singleplayer.install.attempt", value.attempt()));
        var stageLines = font.split(stage, textWidth);
        int contentHeight = 76 + (message.size() + stageLines.size()) * 10;
        int top = Math.max(12, (height - 44 - contentHeight) / 2);
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.mod_name"), width / 2, top, 0xffaaaaaa);
        graphics.centeredText(font, title, width / 2, top + 20, 0xffffffff);
        int y = top + 44;
        for (var line : message) {
            graphics.centeredText(font, line, width / 2, y, 0xffdddddd);
            y += 10;
        }
        y += 12;
        int color = value.stage().equals("failed") ? 0xffff5555 : value.stage().equals("ready") ? 0xff55ff55 : 0xffffd866;
        for (var line : stageLines) {
            graphics.centeredText(font, line, width / 2, y, color);
            y += 10;
        }
        if (value.running()) graphics.centeredText(font, LoadingDotsText.get(System.currentTimeMillis()), width / 2, y + 6, 0xffaaaaaa);
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.python.escape_hint"), width / 2, height - 46, 0xff888888);
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    @Override public void onClose() {
        super.onClose();
        onDismiss.run();
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
    @Override public boolean isPauseScreen() { return false; }
}
