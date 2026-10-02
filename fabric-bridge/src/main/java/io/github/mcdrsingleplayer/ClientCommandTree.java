package io.github.mcdrsingleplayer;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.ArgumentBuilder;
import com.mojang.brigadier.tree.CommandNode;
import java.lang.reflect.Field;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Supplier;
import net.fabricmc.fabric.api.client.command.v2.ClientCommands;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;

/** Rebuild only bridge-owned client roots; MCDR retains parsing and permission authority. */
final class ClientCommandTree {
    private final Supplier<BridgeEndpoint> endpoint;
    private final BiFunction<FabricClientCommandSource, String, Integer> forward;
    private final Set<String> owned = new HashSet<>();
    private CommandDispatcher<FabricClientCommandSource> dispatcher;
    private JsonObject previous;

    ClientCommandTree(Supplier<BridgeEndpoint> endpoint, BiFunction<FabricClientCommandSource, String, Integer> forward) {
        this.endpoint = endpoint;
        this.forward = forward;
    }

    void attach(CommandDispatcher<FabricClientCommandSource> dispatcher) {
        this.dispatcher = dispatcher;
        owned.clear();
        previous = null;
    }

    void tick() {
        if (dispatcher == null) return;
        if (net.minecraft.client.Minecraft.getInstance().getConnection() == null) {
            removeOwned();
            dispatcher = null;
            previous = null;
            return;
        }
        BridgeEndpoint bridge = endpoint.get();
        JsonObject tree = bridge == null ? null : bridge.commandTree;
        if (tree == previous) return;
        removeOwned();
        if (tree != null) {
            JsonArray records = tree.getAsJsonArray("nodes");
            if (records.size() > 20000) throw new IllegalArgumentException("Command graph too large");
            var nodes = new java.util.ArrayList<CommandNode<FabricClientCommandSource>>();
            for (var record : records) nodes.add(build(record.getAsJsonObject()).build());
            try {
                Field redirect = CommandNode.class.getDeclaredField("redirect");
                redirect.setAccessible(true);
                for (int i = 0; i < records.size(); i++) {
                    JsonObject record = records.get(i).getAsJsonObject();
                    for (var child : record.getAsJsonArray("children")) nodes.get(i).addChild(nodes.get(child.getAsInt()));
                    if (!record.get("redirect").isJsonNull()) redirect.set(nodes.get(i), nodes.get(record.get("redirect").getAsInt()));
                }
            } catch (ReflectiveOperationException e) { throw new IllegalStateException("Cannot register MCDR command redirects", e); }
            for (var id : tree.getAsJsonArray("roots")) {
                var node = nodes.get(id.getAsInt());
                String name = node.getName();
                if (dispatcher.getRoot().getChild(name) != null && !owned.contains(name)) continue;
                dispatcher.getRoot().addChild(node);
                owned.add(name);
            }
        }
        previous = tree;
        ClientCommands.refreshCommandCompletions();
    }

    private ArgumentBuilder<FabricClientCommandSource, ?> build(JsonObject value) {
        String name = value.get("name").getAsString();
        boolean literal = "literal".equals(value.get("kind").getAsString());
        boolean greedy = !literal && value.has("greedy") && value.get("greedy").getAsBoolean();
        ArgumentBuilder<FabricClientCommandSource, ?> node;
        if (literal) node = ClientCommands.literal(name);
        else node = ClientCommands.argument(name, greedy ? StringArgumentType.greedyString() : StringArgumentType.string()).suggests(this::suggest);
        node.requires(source -> {
                BridgeEndpoint bridge = endpoint.get();
                return bridge != null && bridge.connected();
            })
            .executes(command -> forward.apply(command.getSource(), command.getInput()));
        if (!greedy) {
            // Custom argument types/recursive redirects keep their complete native behavior.
            node.then(ClientCommands.argument("_mcdr_remaining", StringArgumentType.greedyString())
                .suggests(this::suggest).executes(command -> forward.apply(command.getSource(), command.getInput())));
        }
        return node;
    }

    private java.util.concurrent.CompletableFuture<com.mojang.brigadier.suggestion.Suggestions> suggest(
            com.mojang.brigadier.context.CommandContext<FabricClientCommandSource> command,
            com.mojang.brigadier.suggestion.SuggestionsBuilder builder) {
        BridgeEndpoint bridge = endpoint.get();
        if (bridge == null) return builder.buildFuture();
        return bridge.suggest(command.getSource().getPlayer().getPlainTextName(), builder.getInput()).thenApply(values -> {
            var full = builder.createOffset(0);
            values.forEach(full::suggest);
            return full.build();
        });
    }

    @SuppressWarnings("unchecked")
    private void removeOwned() {
        // Brigadier has no remove API. Its three indexes must agree when a plugin unloads.
        // These unmapped library field names are checked by the real 26.3 game test.
        try {
            for (String index : new String[]{"children", "literals", "arguments"}) {
                Field field = CommandNode.class.getDeclaredField(index);
                field.setAccessible(true);
                Map<String, ?> nodes = (Map<String, ?>) field.get(dispatcher.getRoot());
                owned.forEach(nodes::remove);
            }
        } catch (ReflectiveOperationException e) { throw new IllegalStateException("Cannot refresh MCDR command roots", e); }
        owned.clear();
    }
}
