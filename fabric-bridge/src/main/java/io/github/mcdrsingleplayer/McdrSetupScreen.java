package io.github.mcdrsingleplayer;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.LoadingDotsText;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/**
 * Menu-time MCDR download prompt. Closing it never installs anything and never blocks a save,
 * so the main-menu button can reopen the same information later.
 */
final class McdrSetupScreen extends Screen {
    /** What the menu shows; the runtime is prepared while no save is open, never for one world. */
    enum Status { CHECKING, READY, INSTALLING, FAILED, NEEDS_INSTALL, NEEDS_PYTHON }

    record View(Status status, String reason, InstallProgress progress) { }

    interface Behaviour {
        View view();
        void install();
        void openPython();
        void dismiss();
    }

    private final Behaviour behaviour;

    McdrSetupScreen(Behaviour behaviour) {
        super(Component.translatable("mcdr-singleplayer.setup.title"));
        this.behaviour = behaviour;
    }

    @Override
    protected void init() {
        int buttonWidth = Math.min(200, width - 40);
        int center = (width - buttonWidth) / 2;
        Status status = behaviour.view().status();
        boolean needsPython = status == Status.NEEDS_PYTHON;
        boolean downloadable = status == Status.NEEDS_INSTALL || status == Status.FAILED;
        if (needsPython) {
            addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.setup.python_download"),
                    button -> behaviour.openPython()).bounds(center, height - 56, buttonWidth, 20).build());
        }
        if (downloadable) {
            addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.setup.download"),
                    button -> behaviour.install()).bounds(center, height - 56, buttonWidth, 20).build());
        }
        boolean hasPrimary = needsPython || downloadable;
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.setup.close"), button -> onClose())
                .bounds(center, hasPrimary ? height - 32 : height - 48, buttonWidth, 20).build());
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        graphics.fill(0, 0, width, height, 0x90000000);
        View view = behaviour.view();
        int textWidth = Math.min(360, width - 40);
        int contentHeight = 76 + (view.status() == Status.INSTALLING ? 16 : 0);
        int top = Math.max(12, (height - 44 - contentHeight) / 2);
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.mod_name"), width / 2, top, 0xffaaaaaa);
        graphics.centeredText(font, title, width / 2, top + 20, 0xffffffff);
        int y = top + 44;
        for (var line : font.split(Component.translatable(messageKey(view)), textWidth)) {
            graphics.centeredText(font, line, width / 2, y, 0xffdddddd);
            y += 10;
        }
        if (view.status() == Status.FAILED || view.status() == Status.INSTALLING) {
            InstallProgress progress = view.progress();
            Component stage = Component.translatable(progress.translationKey());
            if (progress.attempt() > 0) stage = stage.copy().append(Component.translatable("mcdr-singleplayer.install.attempt", progress.attempt()));
            for (var line : font.split(stage, textWidth)) {
                graphics.centeredText(font, line, width / 2, y, view.status() == Status.FAILED ? 0xffff5555 : 0xffffd866);
                y += 10;
            }
        }
        if (view.status() == Status.INSTALLING) {
            graphics.centeredText(font, LoadingDotsText.get(System.currentTimeMillis()), width / 2, y + 6, 0xffaaaaaa);
            y += 16;
        }
        // The hint sits above the buttons but below the content, so neither can overlap it.
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.setup.escape_hint"), width / 2,
                Math.min(y + 10, height - 72), 0xff888888);
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    /** One short paragraph per status; the four detected reasons keep their own wording. */
    private static String messageKey(View view) {
        if (view.status() == Status.READY || view.status() == Status.INSTALLING) {
            return "mcdr-singleplayer.setup." + (view.status() == Status.READY ? "ready" : "installing");
        }
        if (view.status() == Status.FAILED) return "mcdr-singleplayer.setup.failed";
        return switch (view.reason()) {
            case McdrSetup.PYTHON_MISSING -> "mcdr-singleplayer.setup.python_missing";
            case "missing" -> "mcdr-singleplayer.setup.missing";
            case "outdated" -> "mcdr-singleplayer.setup.outdated";
            case "broken" -> "mcdr-singleplayer.setup.broken";
            default -> "mcdr-singleplayer.setup.checking";
        };
    }

    @Override public void onClose() {
        behaviour.dismiss();
        super.onClose();
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
    @Override public boolean isPauseScreen() { return false; }
}
