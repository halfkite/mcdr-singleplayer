package io.github.mcdrsingleplayer;

import com.mojang.brigadier.suggestion.Suggestions;
import com.mojang.brigadier.suggestion.SuggestionsBuilder;
import java.util.List;

/** Converts MCDR's complete command strings into ordinary Brigadier token suggestions. */
final class CommandSuggestions {
    private CommandSuggestions() {}

    static Suggestions fromFullCommands(SuggestionsBuilder builder, List<String> commands) {
        String input = builder.getInput();
        int slashOffset = input.startsWith("/") ? 1 : 0;
        String commandInput = input.substring(slashOffset);
        int tokenStart = commandInput.lastIndexOf(' ') + 1;
        SuggestionsBuilder token = builder.createOffset(slashOffset + tokenStart);

        for (String command : commands) {
            String candidate = command.startsWith("/") ? command.substring(1) : command;
            if (candidate.startsWith(commandInput)) {
                token.suggest(candidate.substring(tokenStart));
            }
        }
        return token.build();
    }
}
