package io.github.mcdrsingleplayer;

import java.net.URI;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Blocks the first singleplayer session until a usable Python installation is detected. */
final class PythonSetupScreen extends Screen {
    private static final String PYTHON_VERSION = "3.14.8";
    private static final String WINDOWS_DIRECT = "https://www.python.org/ftp/python/3.14.8/python-3.14.8-amd64.exe";
    private static final String WINDOWS_MIRROR = "https://mirrors.aliyun.com/python-release/windows/python-3.14.8-amd64.exe";
    private static final String DOWNLOADS_PAGE = "https://www.python.org/downloads/";

    PythonSetupScreen() {
        super(Component.translatable("mcdr-singleplayer.python.required_title"));
    }

    @Override
    protected void init() {
        int textWidth = Math.min(360, width - 40);
        var intro = font.split(Component.translatable("mcdr-singleplayer.python.required_intro"), textWidth);
        var instructions = font.split(Component.translatable("mcdr-singleplayer.python.install_instructions"), textWidth);
        var version = Component.translatable("mcdr-singleplayer.python.latest_stable", PYTHON_VERSION);
        int versionLines = font.split(version, textWidth).size();
        int buttonCount = windowsX64() ? 3 : 1;
        int contentHeight = 24 + intro.size() * 10 + 12 + versionLines * 10 + 8
                + instructions.size() * 10 + 10 + buttonCount * 24;
        int top = Math.max(20, (height - contentHeight) / 2);
        int buttonWidth = Math.min(320, width - 40);
        int buttonX = (width - buttonWidth) / 2;
        int y = top + 20 + intro.size() * 10 + 8 + versionLines * 10 + 8 + instructions.size() * 10 + 8;

        if (windowsX64()) {
            addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.python.windows_direct"),
                    button -> open(WINDOWS_DIRECT)).bounds(buttonX, y, buttonWidth, 20).build());
            y += 24;
            addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.python.windows_mirror"),
                    button -> open(WINDOWS_MIRROR)).bounds(buttonX, y, buttonWidth, 20).build());
            y += 24;
        }
        addRenderableWidget(Button.builder(Component.translatable("mcdr-singleplayer.python.other_systems"),
                button -> open(DOWNLOADS_PAGE)).bounds(buttonX, y, buttonWidth, 20).build());
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        int panelWidth = Math.min(400, width - 24);
        int panelLeft = (width - panelWidth) / 2;
        int textWidth = Math.min(360, width - 40);
        var intro = font.split(Component.translatable("mcdr-singleplayer.python.required_intro"), textWidth);
        var instructions = font.split(Component.translatable("mcdr-singleplayer.python.install_instructions"), textWidth);
        var version = font.split(Component.translatable("mcdr-singleplayer.python.latest_stable", PYTHON_VERSION), textWidth);
        int buttonCount = windowsX64() ? 3 : 1;
        int contentHeight = 24 + intro.size() * 10 + 12 + version.size() * 10 + 8
                + instructions.size() * 10 + 10 + buttonCount * 24;
        int top = Math.max(20, (height - contentHeight) / 2);
        int panelBottom = Math.min(height - 12, top + contentHeight);
        graphics.fill(0, 0, width, height, 0x90000000);
        graphics.fill(panelLeft, top - 8, panelLeft + panelWidth, panelBottom + 8, 0xd0101010);
        graphics.fill(panelLeft, top - 8, panelLeft + panelWidth, top - 7, 0xff555555);
        int y = top;
        graphics.centeredText(font, title, width / 2, y, 0xffffffff);
        y += 24;
        for (var line : intro) {
            graphics.centeredText(font, line, width / 2, y, 0xffdddddd);
            y += 10;
        }
        y += 8;
        for (var line : version) {
            graphics.centeredText(font, line, width / 2, y, 0xffffd866);
            y += 10;
        }
        y += 8;
        for (var line : instructions) {
            graphics.centeredText(font, line, width / 2, y, 0xffaaaaaa);
            y += 10;
        }
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    @Override public boolean shouldCloseOnEsc() { return false; }
    @Override public boolean isPauseScreen() { return true; }

    private static boolean windowsX64() {
        String os = System.getProperty("os.name", "").toLowerCase(java.util.Locale.ROOT);
        String arch = System.getProperty("os.arch", "").toLowerCase(java.util.Locale.ROOT);
        return os.contains("windows") && (arch.equals("amd64") || arch.equals("x86_64"));
    }

    private static void open(String url) {
        try { clickUrlAction(Minecraft.getInstance(), Minecraft.getInstance().gui.screen(), URI.create(url)); }
        catch (RuntimeException ignored) { }
    }
}
