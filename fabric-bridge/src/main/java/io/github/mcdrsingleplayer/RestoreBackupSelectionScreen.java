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
        int x = width / 2 - 150;
        int top = Math.max(14, height / 2 - 112);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.restore.retry.back"),
            button -> onClose()).bounds(x, top + 200, 300, 20).build());
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
            addRenderableWidget(Button.builder(backup.id() == selected
                    ? Component.empty().append(Component.literal("> ")).append(backup.label()) : backup.label(), button ->
                Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, "", page, backup.id())))
                .bounds(x, top + 56 + (index % PAGE_SIZE) * 24, 300, 20).build());
        }
        var previous = addRenderableWidget(Button.builder(Component.literal("<"), button ->
            Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, "", page - 1, 0)))
            .bounds(x, top + 174, 28, 20).build());
        previous.active = page > 0;
        var next = addRenderableWidget(Button.builder(Component.literal(">"), button ->
            Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, "", page + 1, 0)))
            .bounds(x + 272, top + 174, 28, 20).build());
        next.active = (page + 1) * PAGE_SIZE < backups.size();
        var confirm = addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.restore.retry.confirm", selected),
            button -> {
                RestoreRecoveryClient.restore(world, selected, reason -> {
                    if (Minecraft.getInstance().gui.screen() instanceof TitleScreen)
                        Minecraft.getInstance().gui.setScreen(new RestoreBackupSelectionScreen(world, backups, reason, page, selected));
                });
                Minecraft.getInstance().gui.setScreen(new TitleScreen());
            }).bounds(x + 36, top + 174, 228, 20).build());
        confirm.active = selected > 0;
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float ticks) {
        int top = Math.max(14, height / 2 - 112);
        graphics.fill(0, 0, width, height, 0xb0000000);
        graphics.centeredText(font, title, width / 2, top - 8, 0xffffffff);
        graphics.centeredText(font, Component.literal(world), width / 2, top + 14, 0xffaaaaaa);
        if (backups == null) graphics.centeredText(font,
            Component.translatable("mcdr-singleplayer.restore.retry.loading"), width / 2, top + 90, 0xffaaaaaa);
        else if (backups.isEmpty() && error.isEmpty()) graphics.centeredText(font,
            Component.translatable("mcdr-singleplayer.restore.retry.empty"), width / 2, top + 90, 0xffaaaaaa);
        if (!error.isEmpty()) {
            int y = top + 28;
            for (var line : font.split(Component.literal(error), Math.min(300, width - 30))) {
                if (y > top + 48) break;
                graphics.centeredText(font, line, width / 2, y, 0xffff7777);
                y += 10;
            }
        }
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.restore.retry.warning"),
            width / 2, top + 158, 0xffffcc66);
        super.extractRenderState(graphics, mouseX, mouseY, ticks);
    }

    @Override public void onClose() { Minecraft.getInstance().gui.setScreen(new TitleScreen()); }
    @Override public boolean shouldCloseOnEsc() { return true; }
}
