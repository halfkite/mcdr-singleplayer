package io.github.mcdrsingleplayer;

import java.util.IdentityHashMap;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.fabricmc.fabric.api.client.screen.v1.Screens;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.LoadingDotsText;
import net.minecraft.util.Util;
import net.minecraft.network.chat.Component;

/** Uses vanilla menu background, loading text and widgets during a restore. */
final class RestoreTitleOverlay {
    static void register(RestoreProgressMonitor monitor) {
        ScreenEvents.AFTER_INIT.register((client, screen, width, height) -> {
            if (!(screen instanceof TitleScreen)) return;
            var background = new Screen(Component.empty()) {};
            background.init(width, height);
            int top = Math.max(24, height / 2 - 65);
            var states = new IdentityHashMap<AbstractWidget, boolean[]>();
            var dismiss = Button.builder(Component.literal(""), button -> monitor.dismiss())
                .bounds(width / 2 - 100, top + 122, 200, 20).build();
            dismiss.visible = false;
            Screens.getWidgets(screen).add(dismiss);
            ScreenEvents.beforeExtract(screen).register((ignored, graphics, mouseX, mouseY, ticks) -> {
                var value = monitor.visible();
                for (var widget : Screens.getWidgets(screen)) {
                    if (widget == dismiss) continue;
                    if (value != null) {
                        states.putIfAbsent(widget, new boolean[]{widget.visible, widget.active});
                        widget.visible = false;
                        widget.active = false;
                    } else if (states.containsKey(widget)) {
                        var previous = states.remove(widget);
                        widget.visible = previous[0];
                        widget.active = previous[1];
                    }
                }
                dismiss.visible = value != null;
                dismiss.active = value != null && !value.running();
            });
            ScreenEvents.afterExtract(screen).register((ignored, graphics, mouseX, mouseY, ticks) -> {
                var value = monitor.visible();
                if (value == null) return;
                int textWidth = Math.min(310, width - 48);
                // Match vanilla loading screens, including resource pack textures.
                graphics.nextStratum();
                background.extractBackground(graphics, mouseX, mouseY, ticks);
                graphics.nextStratum();
                var font = screen.getFont();
                var title = Component.translatable("mcdr-singleplayer.restore.title." + switch (value.status()) {
                    case "completed", "failed", "cancelled" -> value.status();
                    default -> "running";
                });
                graphics.centeredText(font, title, width / 2, top, 0xffffffff);
                graphics.centeredText(font, font.plainSubstrByWidth(value.world() + (value.backup() > 0 ? "  (#" + value.backup() + ")" : ""), textWidth), width / 2, top + 20, 0xffa0a0a0);
                var stage = Component.translatable("mcdr-singleplayer.restore.stage." + switch (value.stage()) {
                    case "checking", "saving", "waiting_files", "safety_backup", "restoring", "rolling_back", "player_data", "completed", "cancelled" -> value.stage();
                    default -> "failed";
                });
                int stageY = top + 42;
                for (var line : font.split(stage, textWidth)) {
                    if (stageY > top + 52) break;
                    graphics.centeredText(font, line, width / 2, stageY, 0xffffffff);
                    stageY += 10;
                }
                if (value.running()) {
                    graphics.centeredText(font, LoadingDotsText.get(Util.getMillis()), width / 2, top + 68, 0xff808080);
                }
                Component detail = value.detail().startsWith("mcdr-singleplayer.")
                    ? Component.translatable(value.detail()) : Component.literal(value.detail());
                if (value.detail().isEmpty()) detail = value.running()
                    ? Component.translatable("mcdr-singleplayer.restore.detail.running")
                    : value.status().equals("completed") ? Component.translatable("mcdr-singleplayer.restore.detail.completed")
                    : value.modified() ? Component.translatable("mcdr-singleplayer.restore.detail.locked") : Component.empty();
                int lineY = top + 90;
                for (var line : font.split(detail, textWidth)) {
                    if (lineY > top + 100) break;
                    graphics.centeredText(font, line, width / 2, lineY, 0xffa0a0a0);
                    lineY += 10;
                }
                dismiss.setMessage(Component.translatable(value.running() ? "mcdr-singleplayer.restore.button.running" : "mcdr-singleplayer.restore.button.menu"));
                graphics.nextStratum();
                dismiss.extractRenderState(graphics, mouseX, mouseY, ticks);
            });
        });
    }
}
