package io.github.mcdrsingleplayer;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.minecraft.network.chat.Component;
import com.mojang.blaze3d.platform.InputConstants;

/** Real rendering and close controls with deterministic installer stages in an isolated world. */
public final class InstallProgressGameTest implements FabricClientGameTest {
    @Override public void runTest(ClientGameTestContext context) {
        if (MultiClientGameTest.selected()) return;
        String original = context.computeOnClient(client -> client.getLanguageManager().getSelected());
        boolean pauseOnLostFocus = context.computeOnClient(client -> client.options.pauseOnLostFocus);
        context.runOnClient(client -> client.options.pauseOnLostFocus = false);
        var value = new AtomicReference<>(new InstallProgress("dependencies", 2));
        var dismissed = new AtomicInteger();
        try (var world = context.worldBuilder().create()) {
            for (String language : new String[]{"zh_cn", "zh_tw", "en_us"}) {
                var reload = context.computeOnClient(client -> {
                    client.getLanguageManager().setSelected(language);
                    return client.reloadResourcePacks();
                });
                context.waitFor(client -> reload.isDone(), 2400);
                value.set(new InstallProgress("dependencies", 2));
                context.setScreen(() -> new McdrInstallNoticeScreen(value::get, dismissed::incrementAndGet));
                context.waitFor(client -> !client.isPaused(), 200);
                context.waitTicks(5);
                context.takeScreenshot("install-progress-" + language);
                context.getInput().pressKey(InputConstants.KEY_ESCAPE);
                context.waitFor(client -> client.gui.screen() == null);
                BridgeGameTest.check(value.get().stage().equals("dependencies"), "Closing cancelled installation");
                context.runOnClient(client -> client.player.sendSystemMessage(Component.translatable(
                        "mcdr-singleplayer.install.chat", Component.translatable(value.get().translationKey()))));
                context.waitTicks(5);
                context.takeScreenshot("install-progress-chat-" + language);
            }
            for (String stage : new String[]{"failed", "ready"}) {
                value.set(new InstallProgress(stage, 0));
                context.setScreen(() -> new McdrInstallNoticeScreen(value::get, dismissed::incrementAndGet));
                context.waitTicks(5);
                context.takeScreenshot("install-progress-" + stage);
                context.clickScreenButton("mcdr-singleplayer.python.close");
                context.waitFor(client -> client.gui.screen() == null);
            }
            BridgeGameTest.check(dismissed.get() == 5, "Close callback did not run exactly once per screen");
        } finally {
            context.runOnClient(client -> client.options.pauseOnLostFocus = pauseOnLostFocus);
            var reload = context.computeOnClient(client -> {
                client.getLanguageManager().setSelected(original);
                return client.reloadResourcePacks();
            });
            context.waitFor(client -> reload.isDone(), 2400);
        }
    }
}
