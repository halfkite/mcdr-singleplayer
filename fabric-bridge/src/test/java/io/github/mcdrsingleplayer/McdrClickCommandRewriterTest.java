package io.github.mcdrsingleplayer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class McdrClickCommandRewriterTest {
    @Test
    void prefixesLegacyRunCommandNestedInTellraw() {
        String input = "execute at @p run tellraw Alex {\"text\":\"help\",\"clickEvent\":{\"action\":\"run_command\",\"value\":\"!!MCDR help\"}}";
        String expected = "execute at @p run tellraw Alex {\"text\":\"help\",\"clickEvent\":{\"action\":\"run_command\",\"value\":\"/!!MCDR help\"}}";

        assertEquals(expected, McdrClickCommandRewriter.addSlash(input));
    }

    @Test
    void prefixesModernSuggestionAndLeavesOtherActionsAlone() {
        String input = "tellraw @a {\"extra\":[{\"text\":\"help\",\"click_event\":{\"action\":\"suggest_command\",\"command\":\"!!pb list\"}}]}";
        String expected = "tellraw @a {\"extra\":[{\"text\":\"help\",\"click_event\":{\"action\":\"suggest_command\",\"command\":\"/!!pb list\"}}]}";

        assertEquals(expected, McdrClickCommandRewriter.addSlash(input));
        assertEquals("tellraw @a {\"text\":\"help\",\"click_event\":{\"action\":\"open_url\",\"url\":\"https://example.com\"}}",
                McdrClickCommandRewriter.addSlash("tellraw @a {\"text\":\"help\",\"click_event\":{\"action\":\"open_url\",\"url\":\"https://example.com\"}}"));
    }

    @Test
    void leavesAlreadySlashedAndNonTellrawCommandsAlone() {
        String alreadySlashed = "tellraw @a {\"text\":\"help\",\"click_event\":{\"action\":\"run_command\",\"command\":\"/!!MCDR help\"}}";
        assertEquals(alreadySlashed, McdrClickCommandRewriter.addSlash(alreadySlashed));
        assertEquals("say !!MCDR help", McdrClickCommandRewriter.addSlash("say !!MCDR help"));
    }
}
