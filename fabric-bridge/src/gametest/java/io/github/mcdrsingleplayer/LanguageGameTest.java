package io.github.mcdrsingleplayer;

import java.util.concurrent.CopyOnWriteArrayList;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.fabric.api.client.command.v2.ClientCommands;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.network.chat.Component;

/** Actual native language reload plus Python chat in independently opened test saves. */
public final class LanguageGameTest implements FabricClientGameTest {
    @Override public void runTest(ClientGameTestContext context) {
        if (System.getenv("MCDR_BRIDGE_TEST_AUTO_COMMON") == null) return;
        var messages = new CopyOnWriteArrayList<String>();
        ClientReceiveMessageEvents.GAME.register((text, overlay) -> messages.add(text.getString()));
        var common = FabricLoader.getInstance().getGameDir().toAbsolutePath().resolve("mcdr-singleplayer");
        String original = context.computeOnClient(client -> client.getLanguageManager().getSelected());
        try {
            for (String language : new String[]{"zh_cn", "zh_tw", "en_us"}) {
                var reload = context.computeOnClient(client -> {
                    client.getLanguageManager().setSelected(language);
                    return client.reloadResourcePacks();
                });
                context.waitFor(client -> reload.isDone(), 2400);
                String expectedTitle = switch (language) {
                    case "zh_cn" -> "回档完成";
                    case "zh_tw" -> "回檔完成";
                    default -> "Restore complete";
                };
                BridgeGameTest.check(context.computeOnClient(client -> Component.translatable("mcdr-singleplayer.restore.title.completed").getString()).equals(expectedTitle), "Native restore translation failed: " + language);
                messages.clear();
                var world = context.worldBuilder().create();
                var profile = common.resolve("date").resolve(world.getWorldSave().getSaveDirectory().getFileName());
                var log = common.resolve("log").resolve(profile.getFileName()).resolve("controller-child.log");
                try (world) {
                    context.waitFor(client -> PrimeBackupGameTest.contains(log, "Singleplayer world ready"), 2400);
                    context.waitFor(client -> ClientCommands.getActiveDispatcher().getRoot().getChild("!!spbridge") != null, 1800);
                    context.runOnClient(client -> client.player.connection.sendCommand("!!spbridge onboarding show"));
                    String expectedButton = switch (language) {
                        case "zh_cn" -> "[开启Prime Backup]";
                        case "zh_tw" -> "[開啟Prime Backup]";
                        default -> "[Enable Prime Backup]";
                    };
                    context.waitFor(client -> messages.stream().anyMatch(text -> text.contains(expectedButton)), 1800);
                    String intro = switch (language) {
                        case "zh_cn" -> "本模组的数据";
                        case "zh_tw" -> "本模組的資料";
                        default -> "Mod data is stored";
                    };
                    BridgeGameTest.check(messages.stream().anyMatch(text -> text.startsWith(intro)), "Python introduction translation failed: " + language);
                    BridgeGameTest.check(messages.stream().filter(text -> text.startsWith(intro)).noneMatch(text -> text.contains("。") || text.endsWith(".")), "Introduction still has full stops");
                    context.takeScreenshot("language-" + language);
                }
                context.waitFor(client -> PrimeBackupGameTest.contains(log, "bye"), 1200);
                context.waitTicks(20);
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
