package io.github.mcdrsingleplayer;

import java.util.List;

/**
 * Position rules for the title-screen icon entry. Flashback occupies the free spot to the right of
 * the vanilla menu buttons, so the entry prefers the free place below that button and only falls
 * back to the right of the menu column when nothing is in the way.
 */
public final class MenuButtonPlacement {
    /** The replay button Flashback adds to the same row; its label key is stable across versions. */
    public static final String FLASHBACK_REPLAY_LABEL = "flashback.open_replays";
    private static final int GAP = 4;
    /** Column offsets tried in order for one row, so the entry fills the free spots left to right. */
    private static final int[] OFFSETS = {0, 1, 2, 3, 4, 5, 6};

    private MenuButtonPlacement() { }

    /** One widget rectangle; only geometry matters here. */
    public record Box(int x, int y, int width, int height, boolean visible) { }

    public record Position(int x, int y) { }

    public static Position place(List<Box> boxes, Box button, Box flashback, int screenWidth, int screenHeight) {
        int size = button.width();
        if (flashback != null) {
            // Same column as the mod that already took the spot, one button height below it.
            int y = flashback.y() + flashback.height() + GAP;
            for (int offset : OFFSETS) {
                int x = flashback.x() + size * offset;
                if (x + size <= screenWidth - GAP && !overlaps(boxes, button, x, y, size)) {
                    return new Position(x, y);
                }
            }
        }
        for (Row row : rows(boxes, screenWidth, screenHeight)) {
            int rowX = row.x() + row.width() + GAP;
            int rowY = row.y() + (row.height() - size) / 2;
            for (int offset : OFFSETS) {
                int x = rowX + size * offset;
                if (x + size > screenWidth - GAP || overlaps(boxes, button, x, rowY, size)) continue;
                return new Position(x, rowY);
            }
        }
        return null;
    }

    /**
     * One entry per button row. {@code x} is the row's left edge, so the right edge of the row is
     * {@code x + width} and the entry starts one gap behind it, stepping right while taken.
     */
    private record Row(int y, int x, int width, int height) { }

    private static List<Row> rows(List<Box> boxes, int screenWidth, int screenHeight) {
        List<Row> rows = new java.util.ArrayList<>();
        for (Box box : boxes) {
            if (!isMenuButton(box, screenWidth, screenHeight)) continue;
            Row current = rows.stream()
                    .filter(row -> Math.abs(row.y() + row.height() / 2 - box.y() - box.height() / 2) <= 2)
                    .findFirst().orElse(null);
            if (current == null) {
                rows.add(new Row(box.y(), box.x(), box.width(), box.height()));
            } else {
                int left = Math.min(current.x(), box.x());
                int right = Math.max(current.x() + current.width(), box.x() + box.width());
                rows.set(rows.indexOf(current), new Row(current.y(), left, right - left, current.height()));
            }
        }
        // The top menu row first, then downward.
        rows.sort(java.util.Comparator.comparingInt(Row::y));
        return rows;
    }

    private static boolean isMenuButton(Box box, int screenWidth, int screenHeight) {
        return box.visible() && box.height() >= 20 && box.y() > screenHeight / 4 && box.x() < screenWidth / 2 + 104;
    }

    private static boolean overlaps(List<Box> boxes, Box self, int x, int y, int size) {
        for (Box other : boxes) {
            if (other == self || !other.visible()) continue;
            if (x < other.x() + other.width() && x + size > other.x()
                    && y < other.y() + other.height() && y + size > other.y()) return true;
        }
        return false;
    }
}
