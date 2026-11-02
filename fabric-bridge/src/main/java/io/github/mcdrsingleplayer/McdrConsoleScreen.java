package io.github.mcdrsingleplayer;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/**
 * The running MCDR console: the newest output lines plus a line to send a command.
 *
 * The controller mirrors the child's console into a small file, so this screen only ever reads it;
 * nothing here can block a running backup or restore.
 */
final class McdrConsoleScreen extends Screen {
    interface Behaviour {
        List<String> lines(int limit);
        void send(String command);
    }

    private static final int REFRESH_MILLIS = 500;
    private static final int LINE_HEIGHT = 10;

    private final Behaviour behaviour;
    private final List<String> lines = new ArrayList<>();
    private EditBox input;
    private long fetchedAt;
    /** Lines scrolled up from the newest one. */
    private int scroll;

    McdrConsoleScreen(Behaviour behaviour) {
        super(Component.translatable("mcdr-singleplayer.console.title"));
        this.behaviour = behaviour;
    }

    @Override
    protected void init() {
        int inputWidth = Math.min(320, width - 40);
        int left = (width - inputWidth) / 2;
        int half = inputWidth / 2 - 2;
        input = new EditBox(font, left, height - 52, inputWidth, 20,
                Component.translatable("mcdr-singleplayer.console.input"));
        input.setMaxLength(256);
        addRenderableWidget(input);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.console.send"),
                button -> submit()).bounds(left, height - 26, half, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.setup.close"),
                button -> onClose()).bounds(left + half + 4, height - 26, half, 20).build());
    }

    private void submit() {
        String command = input == null ? "" : input.getValue().trim();
        if (command.isEmpty()) return;
        behaviour.send(command);
        input.setValue("");
        scroll = 0;
    }

    @Override
    public boolean keyPressed(int keyCode, int scanCode, int modifiers) {
        if (keyCode == 257 || keyCode == 335) {  // Enter, keypad Enter
            submit();
            return true;
        }
        // Arrow keys scroll the log only while the command line is not focused.
        boolean typing = input != null && input.isFocused();
        if (!typing && keyCode == 265) {  // Up
            scroll++;
            return true;
        }
        if (!typing && keyCode == 264) {  // Down
            scroll = Math.max(0, scroll - 1);
            return true;
        }
        return super.keyPressed(keyCode, scanCode, modifiers);
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        refresh();
        graphics.fill(0, 0, width, height, 0xf0101010);
        graphics.centeredText(font, title, width / 2, 12, 0xffffffff);

        int top = 30;
        int bottom = height - 62;
        int capacity = Math.max(1, (bottom - top) / LINE_HEIGHT);
        List<String> shown = window(capacity);
        if (shown.isEmpty()) {
            graphics.centeredText(font, Component.translatable("mcdr-singleplayer.console.empty"),
                    width / 2, top, 0xff888888);
        }
        for (int index = 0; index < shown.size(); index++) {
            // centeredText with a shifted centre keeps one text call across every supported version.
            String text = fit(shown.get(index));
            graphics.centeredText(font, Component.literal(text), 12 + font.width(text) / 2,
                    top + index * LINE_HEIGHT, 0xffcccccc);
        }
        graphics.centeredText(font, Component.translatable("mcdr-singleplayer.console.hint"),
                width / 2, height - 66, 0xff888888);
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    /** Newest {@code capacity} lines, honouring the scroll offset. */
    private List<String> window(int capacity) {
        if (lines.isEmpty()) return List.of();
        int end = Math.max(0, lines.size() - scroll);
        int start = Math.max(0, end - capacity);
        return lines.subList(start, end);
    }

    private void refresh() {
        long now = System.currentTimeMillis();
        if (now - fetchedAt < REFRESH_MILLIS && !lines.isEmpty()) return;
        fetchedAt = now;
        List<String> fresh = behaviour.lines(400);
        lines.clear();
        lines.addAll(fresh);
        scroll = Math.min(scroll, Math.max(0, lines.size() - 1));
    }

    /** Long lines are cut so one message cannot push the rest off screen. */
    private String fit(String text) {
        int limit = Math.max(20, (width - 24) / 6);
        return text.length() <= limit ? text : text.substring(0, limit - 1) + '…';
    }

    @Override public boolean isPauseScreen() { return false; }
    @Override public boolean shouldCloseOnEsc() { return true; }
}
