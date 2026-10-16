package io.github.mcdrsingleplayer;

import java.util.concurrent.CopyOnWriteArrayList;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.minecraft.network.chat.Component;

/**
 * Installation progress inside a world is chat only: entering a save must never open the
 * download prompt, and the stage text has to be translated for every shipped language.
 */
public final class InstallProgressGameTest implements FabricClientGameTest {
    @Override public void runTest(ClientGameTestContext context) {
        if (MultiClientGameTest.selected()) return;
        String original = context.computeOnClient(client -> client.getLanguageManager().getSelected());
        var messages = new CopyOnWriteArrayList<String>();
        ClientReceiveMessageEvents.GAME.register((message, overlay) -> messages.add(message.getString()));
        try (var world = context.worldBuilder().create()) {
            for (String language : new String[]{"zh_cn", "zh_tw", "en_us"}) {
                var reload = context.computeOnClient(client -> {
                    client.getLanguageManager().setSelected(language);
                    return client.reloadResourcePacks();
                });
                context.waitFor(client -> reload.isDone(), 2400);
                messages.clear();
                context.runOnClient(client -> {
                    var progress = new InstallProgress("dependencies", 2);
                    Component stage = Component.translatable(progress.translationKey())
                            .copy().append(Component.translatable("mcdr-singleplayer.install.attempt", progress.attempt()));
                    // The same message the client tick sends while an installation is running.
                    client.player.sendSystemMessage(Component.translatable("mcdr-singleplayer.install.chat", stage));
                });
                context.waitTicks(5);
                BridgeGameTest.check(messages.stream().anyMatch(text -> text.contains("[mcdr-singleplayer]")),
                        "Installation chat is missing: " + language + " " + messages);
                BridgeGameTest.check(messages.stream().noneMatch(text -> text.contains("mcdr-singleplayer.install")),
                        "Installation chat was not translated: " + language + " " + messages);
                BridgeGameTest.check(context.computeOnClient(client -> client.gui.screen() == null),
                        "Installation progress opened a screen inside a world: " + language);
                context.takeScreenshot("install-progress-chat-" + language);
            }
        } finally {
            var reload = context.computeOnClient(client -> {
                client.getLanguageManager().setSelected(original);
                return client.reloadResourcePacks();
            });
            context.waitFor(client -> reload.isDone(), 2400);
        }
    }
}
