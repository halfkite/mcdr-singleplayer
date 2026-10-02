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
                boolean zh = client.getLanguageManager().getSelected().startsWith("zh_");
                int textWidth = Math.min(310, width - 48);
                // Match vanilla loading screens, including resource pack textures.
                graphics.nextStratum();
                background.extractBackground(graphics, mouseX, mouseY, ticks);
                graphics.nextStratum();
                var font = screen.getFont();
                String title = switch (value.status()) {
                    case "completed" -> zh ? "回档完成" : "Restore complete";
                    case "failed" -> zh ? "回档失败" : "Restore failed";
                    case "cancelled" -> zh ? "回档已取消" : "Restore cancelled";
                    default -> zh ? "正在回档" : "Restoring world";
                };
                graphics.centeredText(font, title, width / 2, top, 0xffffffff);
                graphics.centeredText(font, font.plainSubstrByWidth(value.world() + (value.backup() > 0 ? "  (#" + value.backup() + ")" : ""), textWidth), width / 2, top + 20, 0xffa0a0a0);
                String stage = switch (value.stage()) {
                    case "checking" -> zh ? "正在检查备份 / 等待确认" : "Checking backup / waiting for confirmation";
                    case "saving" -> zh ? "正在保存并退出世界" : "Saving and closing the world";
                    case "safety_backup" -> zh ? "正在创建回档前安全备份" : "Creating the pre-restore safety backup";
                    case "restoring" -> zh ? "正在恢复存档并校验文件" : "Restoring and verifying world files";
                    case "completed" -> zh ? "可以重新进入存档" : "You can enter the world.";
                    case "cancelled" -> zh ? "回档已取消或未确认" : "Restore cancelled or not confirmed";
                    default -> zh ? "回档失败，请检查日志" : "Restore failed. Check the logs.";
                };
                int stageY = top + 42;
                for (var line : font.split(Component.literal(stage), textWidth)) {
                    if (stageY > top + 52) break;
                    graphics.centeredText(font, line, width / 2, stageY, 0xffffffff);
                    stageY += 10;
                }
                if (value.running()) {
                    graphics.centeredText(font, LoadingDotsText.get(Util.getMillis()), width / 2, top + 68, 0xff808080);
                }
                String detail = value.detail();
                if (detail.isEmpty()) detail = value.running()
                    ? (zh ? "请等待回档结束；目标存档暂时锁定" : "Please wait. The target world is locked.")
                    : value.status().equals("completed") ? (zh ? "返回主菜单后手动进入原存档" : "Return to the menu and open the restored world.")
                    : value.modified() ? (zh ? "目标存档仍锁定，需要离线重新回档" : "World stays locked. Retry the restore offline.") : "";
                int lineY = top + 90;
                for (var line : font.split(Component.literal(detail), textWidth)) {
                    if (lineY > top + 100) break;
                    graphics.centeredText(font, line, width / 2, lineY, 0xffa0a0a0);
                    lineY += 10;
                }
                dismiss.setMessage(Component.literal(value.running() ? (zh ? "正在回档…" : "Restoring…") : (zh ? "返回主菜单" : "Return to menu")));
                graphics.nextStratum();
                dismiss.extractRenderState(graphics, mouseX, mouseY, ticks);
            });
        });
    }
}
