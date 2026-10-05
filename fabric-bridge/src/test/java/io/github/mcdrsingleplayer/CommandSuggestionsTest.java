package io.github.mcdrsingleplayer;

import com.mojang.brigadier.suggestion.SuggestionsBuilder;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CommandSuggestionsTest {
    @Test
    void replacesOnlyCurrentTokenAndKeepsSlashOutsideReplacement() {
        String input = "/!!MCDR plg br";
        var suggestions = CommandSuggestions.fromFullCommands(
                new SuggestionsBuilder(input, 0), List.of("!!MCDR plg browse", "!!MCDR plg checkupdate"));

        assertEquals(1, suggestions.getList().size());
        assertEquals("browse", suggestions.getList().getFirst().getText());
        assertEquals(input.lastIndexOf(' ') + 1, suggestions.getRange().getStart());
    }

    @Test
    void suggestsNextChildWithoutShowingParentPath() {
        String input = "!!MCDR plg ";
        var suggestions = CommandSuggestions.fromFullCommands(
                new SuggestionsBuilder(input, 0), List.of("!!MCDR plg browse", "!!MCDR plg checkupdate"));

        assertEquals(List.of("browse", "checkupdate"), suggestions.getList().stream().map(value -> value.getText()).toList());
        assertEquals(input.length(), suggestions.getRange().getStart());
    }
}
