package io.github.mcdrsingleplayer;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

/** Adds the slash required by modern Minecraft to MCDR's clickable command text. */
final class McdrClickCommandRewriter {
    private McdrClickCommandRewriter() {}

    static String addSlash(String command) {
        int messageStart = findTellrawMessageStart(command);
        if (messageStart < 0) return command;
        try {
            JsonElement message = JsonParser.parseString(command.substring(messageStart));
            if (!addSlash(message)) return command;
            return command.substring(0, messageStart) + message;
        } catch (com.google.gson.JsonParseException ignored) {
            // Leave unrelated or version-specific tellraw payloads untouched.
            return command;
        }
    }

    private static int findTellrawMessageStart(String command) {
        for (int index = 0; index < command.length();) {
            while (index < command.length() && Character.isWhitespace(command.charAt(index))) index++;
            int tokenStart = index;
            while (index < command.length() && !Character.isWhitespace(command.charAt(index))) index++;
            String token = command.substring(tokenStart, index);
            if (!token.equals("tellraw") && !token.equals("minecraft:tellraw")) continue;
            while (index < command.length() && Character.isWhitespace(command.charAt(index))) index++;
            // MCDR addresses a player name or selector, both a single tellraw target token.
            while (index < command.length() && !Character.isWhitespace(command.charAt(index))) index++;
            while (index < command.length() && Character.isWhitespace(command.charAt(index))) index++;
            if (index < command.length() && (command.charAt(index) == '{' || command.charAt(index) == '[')) return index;
        }
        return -1;
    }

    private static boolean addSlash(JsonElement element) {
        boolean changed = false;
        if (element.isJsonArray()) {
            for (JsonElement child : element.getAsJsonArray()) changed |= addSlash(child);
        } else if (element.isJsonObject()) {
            JsonObject object = element.getAsJsonObject();
            for (String key : new String[]{"click_event", "clickEvent"}) {
                JsonElement event = object.get(key);
                if (event == null || !event.isJsonObject()) continue;
                JsonObject click = event.getAsJsonObject();
                JsonElement action = click.get("action");
                if (action == null || !action.isJsonPrimitive() || !action.getAsJsonPrimitive().isString()) continue;
                String actionName = action.getAsString();
                if (!actionName.equals("run_command") && !actionName.equals("suggest_command")) continue;
                for (String commandKey : new String[]{"command", "value"}) {
                    JsonElement value = click.get(commandKey);
                    if (value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()) {
                        String text = value.getAsString();
                        if (text.startsWith("!!")) {
                            click.addProperty(commandKey, "/" + text);
                            changed = true;
                        }
                    }
                }
            }
            for (var child : object.entrySet()) changed |= addSlash(child.getValue());
        }
        return changed;
    }
}
