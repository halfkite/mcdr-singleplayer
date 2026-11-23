package io.github.mcdrsingleplayer;

import java.util.List;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.chat.Component;

/** Selects one backup of the locked world and requires a separate confirm click. */
final class RestoreBackupSelectionScreen extends Screen {
    private static final int PAGE_SIZE = 4;
    private final String world;
    private final List<RestoreRecoveryClient.Backup> backups;
    private final String error;
    private final int page;
    private final int selected;
    private boolean loading;

    RestoreBackupSelectionScreen(String world) { this(world, null, "", 0, 0); }

    private RestoreBackupSelectionScreen(String world, List<RestoreRecoveryClient.Backup> backups,
            String error, int page, int selected) {
        super(Component.translatable("mcdr-singleplayer.restore.retry.title"));
        this.world = world;
        this.backups = backups;
        this.error = error;
        this.page = page;
        this.selected = selected;
    }

    @Override protected void init() {
        // UI_POLISH_2026
        int x = contentX();
        int listWidth = contentWidth();
        int top = panelY();
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.restore.retry.back"),
            button -> onClose()).bounds(width / 2 - 100, backY(), 200, 20).build());
        if (backups == null) {
            if (!loading) {
                loading = true;
                RestoreRecoveryClient.list(world, result -> {
                    if (Minecraft.getInstance().gui.screen() == this)
                        Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world,
                            result.backups(), result.error(), 0, 0));
                });
            }
            return;
        }
        for (int index = page * PAGE_SIZE; index < Math.min(backups.size(), (page + 1) * PAGE_SIZE); index++) {
            var backup = backups.get(index);
            int rowY = rowY() + (index - page * PAGE_SIZE) * 24;
            var item = addRenderableWidget(Button.builder(backup.id() == selected
                    ? Component.empty().append(Component.literal("> ")).append(backup.label()) : backup.label(), button ->
                Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, "", page, backup.id())))
                .bounds(x, rowY, listWidth, 20).build());
            item.active = true;
        }
        var previous = addRenderableWidget(Button.builder(Component.literal("<"), button ->
            Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, "", page - 1, 0)))
            .bounds(x, pagerY(), 28, 20).build());
        previous.active = page > 0;
        var next = addRenderableWidget(Button.builder(Component.literal(">"), button ->
            Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, "", page + 1, 0)))
            .bounds(x + listWidth - 28, pagerY(), 28, 20).build());
        next.active = (page + 1) * PAGE_SIZE < backups.size();
        var confirm = addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.restore.retry.confirm", selected),
            button -> {
                RestoreRecoveryClient.restore(world, selected, reason -> {
                    if (Minecraft.getInstance().gui.screen() instanceof TitleScreen)
                        Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, reason, page, selected));
                });
                Minecraft.getInstance().gui.setScreen(new TitleScreen());
            }).bounds(x + 34, pagerY(), Math.max(80, listWidth - 68), 20).build());
        confirm.active = selected > 0;
    }

    // UI_POLISH_2026
    private int panelWidth() { return Math.min(560, Math.max(280, width - 20)); }
    private int panelHeight() { return Math.min(236, Math.max(200, height - 16)); }
    private int panelX() { return (width - panelWidth()) / 2; }
    private int panelY() { return (height - panelHeight()) / 2; }
    private int contentX() { return panelX() + 14; }
    private int contentWidth() { return panelWidth() - 28; }
    private int rowY() { return panelY() + 60; }
    private int warningY() { return panelY() + panelHeight() - 66; }
    private int pagerY() { return panelY() + panelHeight() - 52; }
    private int backY() { return panelY() + panelHeight() - 28; }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float ticks) {
        // UI_POLISH_2026
        int panelX = panelX();
        int panelY = panelY();
        int panelWidth = panelWidth();
        int panelHeight = panelHeight();
        int contentX = contentX();
        int contentWidth = contentWidth();
        VanillaConfluxUi.backdrop(graphics, width, height, 0xb0000000);
        VanillaConfluxUi.panel(graphics, panelX, panelY, panelWidth, panelHeight);
        VanillaConfluxUi.accent(graphics, panelX, panelY, panelWidth);
        VanillaConfluxUi.center(graphics, font, title, width / 2, panelY + 12, 0xffffffff);
        String worldLabel = font.plainSubstrByWidth(world, contentWidth);
        VanillaConfluxUi.left(graphics, font, worldLabel, contentX, panelY + 30, 0xffaaaaaa);
        VanillaConfluxUi.divider(graphics, contentX, panelY + 44, contentWidth);

        if (!error.isEmpty()) {
            String shownError = font.plainSubstrByWidth(error, contentWidth);
            VanillaConfluxUi.left(graphics, font, shownError, contentX, panelY + 49, 0xffff7777);
        }
        if (backups == null) {
            VanillaConfluxUi.center(graphics, font,
                    Component.translatable("mcdr-singleplayer.restore.retry.loading"),
                    width / 2, panelY + 104, 0xffaaaaaa);
        } else if (backups.isEmpty() && error.isEmpty()) {
            VanillaConfluxUi.center(graphics, font,
                    Component.translatable("mcdr-singleplayer.restore.retry.empty"),
                    width / 2, panelY + 104, 0xffaaaaaa);
        } else if (!backups.isEmpty()) {
            VanillaConfluxUi.center(graphics, font,
                    Component.translatable("mcdr-singleplayer.restore.retry.warning"),
                    width / 2, warningY(), 0xffffcc66);
        }
        super.extractRenderState(graphics, mouseX, mouseY, ticks);

        if (backups != null && selected > 0) {
            for (int index = page * PAGE_SIZE; index < Math.min(backups.size(), (page + 1) * PAGE_SIZE); index++) {
                if (backups.get(index).id() != selected) continue;
                int y = rowY() + (index - page * PAGE_SIZE) * 24;
                graphics.fill(contentX + 2, y + 3, contentX + 4, y + 17, 0xffd8d8d8);
                break;
            }
        }
    }

    @Override public void onClose() { Minecraft.getInstance().gui.setScreen(new TitleScreen()); }
    @Override public boolean shouldCloseOnEsc() { return true; }
}
