package io.github.mcdrsingleplayer;

import java.util.List;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/**
 * Chunk Backup 建备份前的选区：维度 + 两个角点的区块坐标。
 *
 * 与上游 ``!!cb pmake <x1> <z1> <x2> <z2> in <维度ID>`` 的语义一致，坐标是区块坐标，
 * 两个角的顺序随意。留空坐标表示备份整个维度（type=region，可完整回档）。
 */
public final class ChunkBackupScreen extends Screen {
    /** 确认时带出维度与范围；范围为空表示整维度。取消时传 null。 */
    interface Callback {
        void done(String dimension, int[] region, String comment);
    }

    private static final int WIDTH = 300;
    private final Screen parent;
    private final Callback callback;
    private final List<String> dimensions;
    private int dimensionIndex;
    private EditBox first;
    private EditBox second;
    private EditBox comment;

    private ChunkBackupScreen(Screen parent, List<String> dimensions, Callback callback) {
        super(Component.translatable("mcdr-singleplayer.backup.viewer.chunk_title"));
        this.parent = parent;
        this.dimensions = dimensions;
        this.callback = callback;
    }

    static void open(Screen parent, List<String> dimensions, Callback callback) {
        Minecraft.getInstance().gui.setScreen(new ChunkBackupScreen(parent, dimensions, callback));
    }

    private String dimension() {
        return dimensions.isEmpty() ? "minecraft:overworld" : dimensions.get(dimensionIndex);
    }

    @Override protected void init() {
        int x = width / 2 - WIDTH / 2;
        int top = height / 2 - 80;
        // 维度：点一下在已有维度之间切换，维度列表来自存档的 CB 配置。
        addRenderableWidget(Button.builder(dimensionLabel(), button -> {
            if (dimensions.isEmpty()) return;
            dimensionIndex = (dimensionIndex + 1) % dimensions.size();
            button.setMessage(dimensionLabel());
        }).bounds(x, top + 16, WIDTH, 20).build());
        first = new EditBox(font, x, top + 44, 142, 20,
            Component.translatable("mcdr-singleplayer.backup.viewer.chunk_corner1"));
        first.setHint(Component.translatable("mcdr-singleplayer.backup.viewer.chunk_corner1"));
        addRenderableWidget(first);
        second = new EditBox(font, x + 158, top + 44, 142, 20,
            Component.translatable("mcdr-singleplayer.backup.viewer.chunk_corner2"));
        second.setHint(Component.translatable("mcdr-singleplayer.backup.viewer.chunk_corner2"));
        addRenderableWidget(second);
        comment = new EditBox(font, x, top + 72, WIDTH, 20,
            Component.translatable("mcdr-singleplayer.backup.viewer.comment_hint"));
        comment.setMaxLength(96);
        comment.setHint(Component.translatable("mcdr-singleplayer.backup.viewer.comment_optional"));
        addRenderableWidget(comment);
        setInitialFocus(first);
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.chunk_ok"),
            button -> confirm()).bounds(x, top + 104, 142, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.backup.viewer.back"),
            button -> cancel()).bounds(x + 158, top + 104, 142, 20).build());
    }

    private Component dimensionLabel() {
        return Component.translatable("mcdr-singleplayer.backup.viewer.chunk_dimension",
            Component.literal(dimension()));
    }

    /** 两个角点都填了才当成选区，否则整维度备份。 */
    private void confirm() {
        String left = first == null ? "" : first.getValue().strip();
        String right = second == null ? "" : second.getValue().strip();
        String text = comment == null ? "" : comment.getValue().strip();
        int[] region = null;
        if (!left.isEmpty() || !right.isEmpty()) {
            region = parse(left, right);
            if (region == null) {
                // 坐标不合法就停在原界面，让用户改，而不是静默退回整维度备份。
                if (first != null) first.setValue(left.isEmpty() ? "0 0" : left);
                return;
            }
        }
        String dim = dimension();
        Minecraft.getInstance().gui.setScreen(parent);
        callback.done(dim, region, text);
    }

    /** 接受 "x z" 与 "x,z" 两种写法；两个角点合起来必须正好四个数字。 */
    private static int[] parse(String left, String right) {
        var numbers = new java.util.ArrayList<Integer>();
        for (var part : (left + " " + right).trim().split("[\\s,]+")) {
            if (part.isEmpty()) continue;
            try {
                numbers.add(Integer.parseInt(part));
            } catch (NumberFormatException error) {
                return null;
            }
        }
        if (numbers.size() != 4) return null;
        return new int[] {numbers.get(0), numbers.get(1), numbers.get(2), numbers.get(3)};
    }

    private void cancel() {
        Minecraft.getInstance().gui.setScreen(parent);
        callback.done(null, null, null);
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float ticks) {
        // UI_POLISH_2026
        int top = height / 2 - 80;
        int panelX = width / 2 - WIDTH / 2 - 12;
        int panelY = top - 16;
        int panelWidth = WIDTH + 24;
        VanillaConfluxUi.backdrop(graphics, width, height, 0xc0000000);
        VanillaConfluxUi.panel(graphics, panelX, panelY, panelWidth, 172);
        VanillaConfluxUi.accent(graphics, panelX, panelY, panelWidth);
        VanillaConfluxUi.center(graphics, font, title, width / 2, top, 0xffffffff);
        VanillaConfluxUi.divider(graphics, panelX + 12, top + 12, panelWidth - 24);
        VanillaConfluxUi.divider(graphics, panelX + 18, top + 124, panelWidth - 36);
        var help = font.split(Component.translatable("mcdr-singleplayer.backup.viewer.chunk_help"), panelWidth - 28);
        int y = top + 130;
        for (var line : help) {
            VanillaConfluxUi.center(graphics, font, line, width / 2, y, 0xffa0a0a0);
            y += 10;
        }
        super.extractRenderState(graphics, mouseX, mouseY, ticks);
    }

    @Override public void onClose() {
        cancel();
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
}
