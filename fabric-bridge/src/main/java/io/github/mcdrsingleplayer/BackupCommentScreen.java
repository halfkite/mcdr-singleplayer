package io.github.mcdrsingleplayer;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/**
 * 备份前填写备注的小弹窗，也可以留空直接确认。
 *
 * 单独做一个界面而不是在查看器里塞输入框：查看器自己会重绘整个版面，输入框
 * 在重排时容易丢焦点；这个弹窗只在打开期间存在，确认或取消后回到查看器。
 */
public final class BackupCommentScreen extends Screen {
    /** 确认时带出备注（可能为空）；取消时传 null。 */
    interface Callback {
        void done(String comment);
    }

    private static final int WIDTH = 260;
    private final Screen parent;
    private final Callback callback;
    private final String hint;
    private EditBox field;

    private BackupCommentScreen(Screen parent, String hint, Callback callback) {
        super(Component.translatable("mcdr-singleplayer.backup.viewer.comment_title"));
        this.parent = parent;
        this.hint = hint;
        this.callback = callback;
    }

    static void open(Screen parent, String hint, Callback callback) {
        Minecraft.getInstance().gui.setScreen(new BackupCommentScreen(parent, hint, callback));
    }

    @Override protected void init() {
        int x = width / 2 - WIDTH / 2;
        int top = height / 2 - 40;
        field = new EditBox(font, x, top + 20, WIDTH, 20,
            Component.translatable("mcdr-singleplayer.backup.viewer.comment_hint"));
        field.setMaxLength(96);
        field.setHint(Component.translatable("mcdr-singleplayer.backup.viewer.comment_optional"));
        addRenderableWidget(field);
        setInitialFocus(field);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.comment_ok"),
            button -> confirm()).bounds(x, top + 48, 124, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.back"),
            button -> cancel()).bounds(x + 136, top + 48, 124, 20).build());
    }

    private void confirm() {
        String value = field == null ? "" : field.getValue().strip();
        Minecraft.getInstance().gui.setScreen(parent);
        callback.done(value);
    }

    private void cancel() {
        Minecraft.getInstance().gui.setScreen(parent);
        callback.done(null);
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float ticks) {
        graphics.fill(0, 0, width, height, 0xc0000000);
        int top = height / 2 - 40;
        graphics.centeredText(font, title, width / 2, top, 0xffffffff);
        if (!hint.isEmpty()) {
            graphics.centeredText(font, localized(hint), width / 2, top + 12, 0xffa0a0a0);
        }
        super.extractRenderState(graphics, mouseX, mouseY, ticks);
    }

    private static Component localized(String text) {
        return text.startsWith("mcdr-singleplayer.") ? Component.translatable(text) : Component.literal(text);
    }

    @Override public void onClose() {
        cancel();
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
}
