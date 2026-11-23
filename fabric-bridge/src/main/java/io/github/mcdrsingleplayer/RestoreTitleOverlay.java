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
            var retry = Button.builder(Component.translatable("mcdr-singleplayer.restore.retry.button"), button -> {
                var value = monitor.visible();
                if (value != null && value.status().equals("failed"))
                    client.gui.setScreen(new RestoreBackupSelectionScreen(value.world()));
            }).bounds(width / 2 - 100, top + 122, 200, 20).build();
            retry.visible = false;
            Screens.getWidgets(screen).add(retry);
            var dismiss = Button.builder(Component.literal(""), button -> monitor.dismiss())
                .bounds(width / 2 - 100, top + 146, 200, 20).build();
            dismiss.visible = false;
            Screens.getWidgets(screen).add(dismiss);
            ScreenEvents.beforeExtract(screen).register((ignored, graphics, mouseX, mouseY, ticks) -> {
                var value = monitor.visible();
                for (var widget : Screens.getWidgets(screen)) {
                    if (widget == dismiss || widget == retry) continue;
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
                retry.visible = value != null && value.status().equals("failed");
                retry.active = retry.visible;
            });
            ScreenEvents.afterExtract(screen).register((ignored, graphics, mouseX, mouseY, ticks) -> {
                var value = monitor.visible();
                if (value == null) return;
                int panelWidth = Math.min(420, width - 24);
                int panelX = (width - panelWidth) / 2;
                int panelY = top - 14;
                int textWidth = Math.min(310, panelWidth - 32);

                // 继续使用原版标题界面的全景背景，只在进度信息下增加中性灰面板。
                graphics.nextStratum();
                background.extractBackground(graphics, mouseX, mouseY, ticks);
                graphics.nextStratum();
                VanillaConfluxUi.panel(graphics, panelX, panelY, panelWidth, 184);
                VanillaConfluxUi.accent(graphics, panelX, panelY, panelWidth);

                var font = screen.getFont();
                String statusKey = switch (value.status()) {
                    case "completed", "failed", "cancelled" -> value.status();
                    default -> "running";
                };
                var title = Component.translatable("mcdr-singleplayer.restore.title." + statusKey);
                int titleColor = value.status().equals("failed") ? 0xffff7777
                        : value.status().equals("completed") ? 0xffc6e3c6 : 0xffffffff;
                VanillaConfluxUi.center(graphics, font, title, width / 2, top, titleColor);

                String world = value.world() + (value.backup() > 0 ? "  (#" + value.backup() + ")" : "");
                VanillaConfluxUi.center(graphics, font,
                        Component.literal(font.plainSubstrByWidth(world, textWidth)),
                        width / 2, top + 20, 0xffa0a0a0);
                VanillaConfluxUi.divider(graphics, panelX + 18, top + 34, panelWidth - 36);

                var stage = Component.translatable("mcdr-singleplayer.restore.stage." + switch (value.stage()) {
                    case "checking", "saving", "waiting_files", "safety_backup", "restoring", "rolling_back",
                            "player_data", "completed", "cancelled" -> value.stage();
                    default -> "failed";
                });
                int stageY = top + 42;
                for (var line : font.split(stage, textWidth)) {
                    if (stageY > top + 52) break;
                    VanillaConfluxUi.center(graphics, font, line, width / 2, stageY, 0xffffffff);
                    stageY += 10;
                }
                if (value.running()) {
                    VanillaConfluxUi.center(graphics, font,
                            LoadingDotsText.get(Util.getMillis()), width / 2, top + 68, 0xffaaaaaa);
                }

                Component detail = value.detail().startsWith("mcdr-singleplayer.")
                        ? Component.translatable(value.detail()) : Component.literal(value.detail());
                if (value.detail().isEmpty()) {
                    detail = value.running()
                            ? Component.translatable("mcdr-singleplayer.restore.detail.running")
                            : value.status().equals("completed")
                                    ? Component.translatable("mcdr-singleplayer.restore.detail.completed")
                                    : value.modified()
                                            ? Component.translatable("mcdr-singleplayer.restore.detail.locked")
                                            : Component.empty();
                }
                int lineY = top + 90;
                for (var line : font.split(detail, textWidth)) {
                    if (lineY > top + 100) break;
                    VanillaConfluxUi.center(graphics, font, line, width / 2, lineY, 0xffa0a0a0);
                    lineY += 10;
                }
                dismiss.setMessage(Component.translatable(value.running()
                        ? "mcdr-singleplayer.restore.button.running" : "mcdr-singleplayer.restore.button.menu"));
                graphics.nextStratum();
                if (retry.visible) retry.extractRenderState(graphics, mouseX, mouseY, ticks);
                dismiss.extractRenderState(graphics, mouseX, mouseY, ticks);
            });
        });
    }
}
