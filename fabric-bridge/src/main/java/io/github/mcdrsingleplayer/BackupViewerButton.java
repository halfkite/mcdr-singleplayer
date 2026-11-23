package io.github.mcdrsingleplayer;

import java.util.List;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.fabricmc.fabric.api.client.screen.v1.Screens;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.worldselection.EditWorldScreen;
import net.minecraft.network.chat.Component;

/**
 * 在单个存档的编辑界面加一个「查看存档」入口。
 *
 * 用 Screen API 的事件挂载，而不是往 EditWorldScreen 里注入：widget 注册方法在
 * Screen 上是泛型的，mixin 用 @Shadow 去要会被擦除成 GuiEventListener，在目标类里
 * 找不到而让整个界面类转换失败（点「编辑」直接报错）。这里只让 mixin 读一个字段，
 * 添加按钮走 Fabric 的事件接口，不碰原版界面。
 *
 * 位置取自原版按钮本身：这个界面的按钮在 LinearLayout 里整体居中，纵向位置随窗口
 * 高度变化，所以按列内最后一行按钮的实际矩形往下排，而不是硬编码偏移。
 *
 * AFTER_INIT 会在窗口缩放等情况下对同一个界面再次触发，所以先查这个界面里有没有
 * 自己加的按钮：已经有就只重新定位，绝不重复添加（否则会堆出好几个入口）。
 */
final class BackupViewerButton {
    private BackupViewerButton() {}

    static void register() {
        ScreenEvents.AFTER_INIT.register((client, screen, width, height) -> {
            if (!(screen instanceof EditWorldScreen editor)) return;
            if (!(editor instanceof BackupViewerAccess access)) return;
            String world = access.mcdr$worldId();
            if (world == null || world.isEmpty()) return;
            var widgets = Screens.getWidgets(screen);
            Button button = existing(widgets);
            if (button == null) {
                button = Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.button"),
                    pressed -> BackupViewerScreen.open(world, editor)).build();
                widgets.add(button);
            }
            place(widgets, button, width, height);
        });
    }

    /** 已经加过的入口；用文案识别，不额外保存状态。 */
    private static Button existing(List<AbstractWidget> widgets) {
        String label = Component.translatable("mcdr-singleplayer.backup.viewer.button").getString();
        for (var widget : widgets) {
            if (!(widget instanceof Button candidate)) continue;
            if (candidate.getMessage().getString().equals(label)) return candidate;
        }
        return null;
    }

    /** 贴着原版按钮列的最末一行往下放，宽度与那一列一致。 */
    private static void place(List<AbstractWidget> widgets, Button button, int width, int height) {
        AbstractWidget last = null;
        int column = -1;
        String own = button.getMessage().getString();
        for (var widget : widgets) {
            if (widget == button) continue;
            if (widget instanceof Button candidate && candidate.getMessage().getString().equals(own)) continue;
            // 只认原版按钮列：宽 200 左右、横向居中，排除图标按钮。
            if (widget.getWidth() < 120) continue;
            if (last == null || widget.getY() >= last.getY()) {
                last = widget;
                column = widget.getWidth();
            }
        }
        int buttonWidth = column > 0 ? column : Math.min(200, Math.max(120, width - 40));
        int x = width / 2 - buttonWidth / 2;
        int y = last != null ? last.getY() + last.getHeight() + 4 : height / 2 + 74;
        // 屏幕很矮时不要压到边缘，宁可贴底。
        y = Math.min(y, height - 28);
        button.setWidth(buttonWidth);
        button.setX(x);
        button.setY(y);
    }
}
