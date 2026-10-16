package io.github.mcdrsingleplayer;

import java.util.concurrent.atomic.AtomicInteger;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.screen.v1.Screens;
import net.minecraft.network.chat.Component;
import net.minecraft.client.gui.components.AbstractWidget;

/**
 * Menu-time download prompt: rendered per language and per status, closable, and it never installs
 * on close. It prepares the shared runtime, so it must not talk about connecting a save.
 */
public final class McdrSetupGameTest implements FabricClientGameTest {
    private record Behaviour(McdrSetupScreen.View view, AtomicInteger installs, AtomicInteger dismissals)
            implements McdrSetupScreen.Behaviour {
        @Override public void install() { installs.incrementAndGet(); }

        @Override public void dismiss() { dismissals.incrementAndGet(); }
    }

    @Override public void runTest(ClientGameTestContext context) {
        if (MultiClientGameTest.selected()) return;
        String original = context.computeOnClient(client -> client.getLanguageManager().getSelected());
        boolean pauseOnLostFocus = context.computeOnClient(client -> client.options.pauseOnLostFocus);
        context.runOnClient(client -> client.options.pauseOnLostFocus = false);
        var installs = new AtomicInteger();
        var dismissals = new AtomicInteger();
        var current = new Behaviour[] {null};
        int screens = 0;
        String download = Component.translatable("mcdr-singleplayer.setup.download").getString();
        String connection = Component.translatable("mcdr-singleplayer.install.chat").getString().split("%")[0];
        try {
            for (String language : new String[]{"zh_cn", "zh_tw", "en_us"}) {
                var reload = context.computeOnClient(client -> {
                    client.getLanguageManager().setSelected(language);
                    return client.reloadResourcePacks();
                });
                context.waitFor(client -> reload.isDone(), 2400);
                for (McdrSetupScreen.View view : views()) {
                    current[0] = new Behaviour(view, installs, dismissals);
                    context.setScreen(() -> new McdrSetupScreen(current[0]));
                    context.waitFor(client -> !client.isPaused(), 200);
                    context.waitTicks(5);
                    boolean actionable = view.status() == McdrSetupScreen.Status.NEEDS_INSTALL
                            || view.status() == McdrSetupScreen.Status.FAILED;
                    boolean offered = context.computeOnClient(client -> Screens.getWidgets(client.gui.screen()).stream()
                            .anyMatch(widget -> widget.active && widget.getMessage().getString().equals(download)));
                    BridgeGameTest.check(offered == actionable, "Download button visibility is wrong for " + view.status());
                    // This screen prepares the shared runtime; only chat may mention a save.
                    BridgeGameTest.check(context.computeOnClient(client -> Screens.getWidgets(client.gui.screen()).stream()
                                    .noneMatch(widget -> widget.getMessage().getString().contains(connection))),
                            "The menu prompt mentions connecting a save: " + view.status());
                    context.takeScreenshot("mcdr-setup-" + view.status().name().toLowerCase(java.util.Locale.ROOT) + "-" + language);
                    context.clickScreenButton("mcdr-singleplayer.setup.close");
                    context.waitFor(client -> client.gui.screen() == null);
                    screens++;
                }
            }
            BridgeGameTest.check(dismissals.get() == screens, "Close callback did not run once per screen: " + dismissals.get());
            BridgeGameTest.check(installs.get() == 0, "Closing the prompt started an installation");

            // Esc must dismiss the prompt without starting any download.
            current[0] = new Behaviour(needsInstall("missing"), installs, dismissals);
            context.setScreen(() -> new McdrSetupScreen(current[0]));
            context.waitTicks(5);
            context.getInput().pressKey(com.mojang.blaze3d.platform.InputConstants.KEY_ESCAPE);
            context.waitFor(client -> client.gui.screen() == null);
            BridgeGameTest.check(dismissals.get() == screens + 1, "Esc did not dismiss the prompt");
            BridgeGameTest.check(installs.get() == 0, "Esc started an installation");

            // The download button installs and closes the prompt it belongs to.
            current[0] = new Behaviour(needsInstall("missing"), installs, dismissals);
            context.setScreen(() -> new McdrSetupScreen(current[0]));
            context.waitTicks(5);
            context.clickScreenButton("mcdr-singleplayer.setup.download");
            context.waitTicks(5);
            BridgeGameTest.check(installs.get() == 1, "The download button did not request an installation");
        } finally {
            context.runOnClient(client -> client.options.pauseOnLostFocus = pauseOnLostFocus);
            var reload = context.computeOnClient(client -> {
                client.getLanguageManager().setSelected(original);
                return client.reloadResourcePacks();
            });
            context.waitFor(client -> reload.isDone(), 2400);
        }
    }

    private static McdrSetupScreen.View[] views() {
        return new McdrSetupScreen.View[]{
                new McdrSetupScreen.View(McdrSetupScreen.Status.CHECKING, "",
                        new InstallProgress("preparing", 0)),
                needsInstall("missing"),
                needsInstall("outdated"),
                needsInstall("broken"),
                new McdrSetupScreen.View(McdrSetupScreen.Status.FAILED, "failed",
                        new InstallProgress("failed", 0)),
                new McdrSetupScreen.View(McdrSetupScreen.Status.INSTALLING, "missing",
                        new InstallProgress("dependencies", 2)),
                new McdrSetupScreen.View(McdrSetupScreen.Status.READY, McdrSetup.READY,
                        new InstallProgress("ready", 0))};
    }

    private static McdrSetupScreen.View needsInstall(String reason) {
        return new McdrSetupScreen.View(McdrSetupScreen.Status.NEEDS_INSTALL, reason,
                new InstallProgress("preparing", 0));
    }
}
