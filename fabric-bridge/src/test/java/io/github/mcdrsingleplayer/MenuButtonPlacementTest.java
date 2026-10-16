package io.github.mcdrsingleplayer;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * The icon entry must not end up under Flashback's replay button, which takes the spot right of the
 * vanilla menu column first, and it must never be drawn on top of another widget.
 */
class MenuButtonPlacementTest {
    private static final int SCREEN_WIDTH = 480;
    private static final int SCREEN_HEIGHT = 270;
    private static final int SIZE = 20;

    @Test void anotherModBesideTheColumnPushesTheEntryToTheNextColumn() {
        List<MenuButtonPlacement.Box> boxes = vanillaTitleScreen();
        MenuButtonPlacement.Position position = MenuButtonPlacement.place(boxes, ownButton(), null,
                SCREEN_WIDTH, SCREEN_HEIGHT);
        assertNotNull(position);
        // The mods column ends at 334, so the first free column starts one gap behind it.
        assertEquals(new MenuButtonPlacement.Position(338, 80), position);
    }

    @Test void flashbackKeepsItsSpotAndTheEntryMovesBelowIt() {
        List<MenuButtonPlacement.Box> boxes = vanillaTitleScreen();
        MenuButtonPlacement.Box flashback = new MenuButtonPlacement.Box(314, 80, SIZE, SIZE, true);
        boxes.add(flashback);
        MenuButtonPlacement.Position position = MenuButtonPlacement.place(boxes, ownButton(), flashback,
                SCREEN_WIDTH, SCREEN_HEIGHT);
        assertNotNull(position);
        // Directly below the replay button, in the same column it uses.
        assertEquals(new MenuButtonPlacement.Position(314, 104), position);
        assertFalse(overlaps(boxes, position), "The entry overlaps another button");
    }

    @Test void theEntryNeverOverlapsAnyVisibleWidget() {
        for (boolean withFlashback : new boolean[]{false, true}) {
            for (boolean crowded : new boolean[]{false, true}) {
                List<MenuButtonPlacement.Box> boxes = vanillaTitleScreen();
                MenuButtonPlacement.Box flashback = null;
                if (withFlashback) {
                    flashback = new MenuButtonPlacement.Box(314, 80, SIZE, SIZE, true);
                    boxes.add(flashback);
                }
                if (crowded) {
                    boxes.add(new MenuButtonPlacement.Box(334, 80, SIZE, SIZE, true));
                    boxes.add(new MenuButtonPlacement.Box(354, 80, SIZE, SIZE, true));
                }
                MenuButtonPlacement.Position position = MenuButtonPlacement.place(boxes, ownButton(), flashback,
                        SCREEN_WIDTH, SCREEN_HEIGHT);
                assertNotNull(position, "No placement found (flashback=" + withFlashback + ", crowded=" + crowded + ")");
                assertFalse(overlaps(boxes, position), "Overlap with flashback=" + withFlashback + ", crowded=" + crowded);
                assertTrue(position.x() + SIZE <= SCREEN_WIDTH - 4, "The entry leaves the screen");
                assertTrue(position.y() + SIZE <= SCREEN_HEIGHT, "The entry leaves the screen");
            }
        }
    }

    @Test void anInvisibleWidgetDoesNotBlockThePlacement() {
        List<MenuButtonPlacement.Box> boxes = vanillaTitleScreen();
        boxes.add(new MenuButtonPlacement.Box(314, 80, SIZE, SIZE, false));
        assertEquals(new MenuButtonPlacement.Position(338, 80),
                MenuButtonPlacement.place(boxes, ownButton(), null, SCREEN_WIDTH, SCREEN_HEIGHT));
    }

    private static MenuButtonPlacement.Box ownButton() {
        return new MenuButtonPlacement.Box(0, 0, SIZE, SIZE, true);
    }

    /**
     * Vanilla 480x270 title screen: the menu column, the mods/realms column that shares the row of
     * the first button, and the options/quit row at the bottom.
     */
    private static List<MenuButtonPlacement.Box> vanillaTitleScreen() {
        List<MenuButtonPlacement.Box> boxes = new ArrayList<>();
        boxes.add(new MenuButtonPlacement.Box(110, 80, 200, 20, true));   // Singleplayer
        boxes.add(new MenuButtonPlacement.Box(110, 104, 200, 20, true));  // Multiplayer
        boxes.add(new MenuButtonPlacement.Box(110, 128, 200, 20, true));  // Realms
        boxes.add(new MenuButtonPlacement.Box(110, 152, 200, 20, true));  // Mods
        boxes.add(new MenuButtonPlacement.Box(110, 202, 98, 20, true));   // Options
        boxes.add(new MenuButtonPlacement.Box(212, 202, 98, 20, true));   // Quit
        boxes.add(new MenuButtonPlacement.Box(314, 80, 20, 20, true));    // Realms notifications
        return boxes;
    }

    private static boolean overlaps(List<MenuButtonPlacement.Box> boxes, MenuButtonPlacement.Position position) {
        for (MenuButtonPlacement.Box box : boxes) {
            if (!box.visible()) continue;
            if (position.x() < box.x() + box.width() && position.x() + SIZE > box.x()
                    && position.y() < box.y() + box.height() && position.y() + SIZE > box.y()) return true;
        }
        return false;
    }
}
