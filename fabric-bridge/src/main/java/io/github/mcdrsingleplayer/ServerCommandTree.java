package io.github.mcdrsingleplayer;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.ArgumentBuilder;
import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.brigadier.builder.RequiredArgumentBuilder;
import com.mojang.brigadier.tree.CommandNode;
import java.lang.reflect.Field;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;

/** Vanilla command packets make the host's MCDR commands usable by LAN guests. */
final class ServerCommandTree {
    private final Supplier<BridgeEndpoint> endpoint;
    private final Set<String> owned = new HashSet<>();
    private MinecraftServer server;
    private JsonObject previous;

    ServerCommandTree(Supplier<BridgeEndpoint> endpoint) { this.endpoint = endpoint; }

    void attach(MinecraftServer server) {
        this.server = server;
        owned.clear();
        previous = null;
    }

    void stop() { server = null; owned.clear(); previous = null; }

    @SuppressWarnings("unchecked")
    void tick(MinecraftServer current) {
        if (server != current) return;
        BridgeEndpoint bridge = endpoint.get();
        JsonObject tree = bridge != null && bridge.connected() ? bridge.commandTree : null;
        if (tree == previous) return;
        var dispatcher = server.getCommands().getDispatcher();
        try {
            for (String index : new String[]{"children", "literals", "arguments"}) {
                Field field = CommandNode.class.getDeclaredField(index);
                field.setAccessible(true);
                Map<String, ?> roots = (Map<String, ?>) field.get(dispatcher.getRoot());
                owned.forEach(roots::remove);
            }
            owned.clear();
            if (tree != null) {
                JsonArray records = tree.getAsJsonArray("nodes");
                if (records.size() > 20000) throw new IllegalArgumentException("Command graph too large");
                var nodes = new java.util.ArrayList<CommandNode<CommandSourceStack>>();
                for (var record : records) nodes.add(build(record.getAsJsonObject()).build());
                Field redirect = CommandNode.class.getDeclaredField("redirect");
                redirect.setAccessible(true);
                for (int i = 0; i < records.size(); i++) {
                    JsonObject record = records.get(i).getAsJsonObject();
                    for (var child : record.getAsJsonArray("children")) nodes.get(i).addChild(nodes.get(child.getAsInt()));
                    if (!record.get("redirect").isJsonNull()) redirect.set(nodes.get(i), nodes.get(record.get("redirect").getAsInt()));
                }
                for (var id : tree.getAsJsonArray("roots")) {
                    var node = nodes.get(id.getAsInt());
                    if (dispatcher.getRoot().getChild(node.getName()) != null) continue;
                    dispatcher.getRoot().addChild(node);
                    owned.add(node.getName());
                }
            }
        } catch (ReflectiveOperationException e) { throw new IllegalStateException("Cannot refresh LAN MCDR commands", e); }
        previous = tree;
        server.getPlayerList().getPlayers().forEach(player -> server.getCommands().sendCommands(player));
    }

    private ArgumentBuilder<CommandSourceStack, ?> build(JsonObject value) {
        String name = value.get("name").getAsString();
        boolean literal = "literal".equals(value.get("kind").getAsString());
        boolean greedy = !literal && value.has("greedy") && value.get("greedy").getAsBoolean();
        ArgumentBuilder<CommandSourceStack, ?> node = literal
            ? LiteralArgumentBuilder.<CommandSourceStack>literal(name)
            : RequiredArgumentBuilder.<CommandSourceStack, String>argument(name,
                greedy ? StringArgumentType.greedyString() : StringArgumentType.string());
        node.requires(source -> source.getEntity() instanceof ServerPlayer && endpoint.get() != null && endpoint.get().connected())
            .executes(command -> {
                BridgeEndpoint bridge = endpoint.get();
                if (command.getSource().getEntity() instanceof ServerPlayer player
                        && bridge != null && bridge.clientChat(player.getPlainTextName(), command.getInput())) return 1;
                command.getSource().sendFailure(Component.translatable("mcdr-singleplayer.client.no_connection"));
                return 0;
            });
        // Only this fallback asks the server for suggestions. If each mirrored
        // argument also used ASK_SERVER, vanilla would cancel the earlier request
        // while Brigadier was still waiting for all sibling providers to finish.
        if (!greedy) node.then(RequiredArgumentBuilder.<CommandSourceStack, String>argument("_mcdr_remaining", StringArgumentType.greedyString())
            .suggests(this::suggest).executes(node.getCommand()));
        return node;
    }

    private java.util.concurrent.CompletableFuture<com.mojang.brigadier.suggestion.Suggestions> suggest(
            com.mojang.brigadier.context.CommandContext<CommandSourceStack> command,
            com.mojang.brigadier.suggestion.SuggestionsBuilder builder) {
        BridgeEndpoint bridge = endpoint.get();
        if (bridge == null || !(command.getSource().getEntity() instanceof ServerPlayer player)) return builder.buildFuture();
        String input = builder.getInput();
        boolean slash = input.startsWith("/");
        return bridge.suggest(player.getPlainTextName(), slash ? input.substring(1) : input).thenApply(values -> {
            return CommandSuggestions.fromFullCommands(builder, values);
        });
    }
}
