from pitxu.lib.objects import Rectangle, Point

import math

class BarsGeometry:
    """
    The geometry of the background effects (the KITT mouth, the countdown and the scanner), that are drawn as
    rectangles. There is no grid: everything is proportional to the area that they are drawn in.

    The shared rule is the outer margin, a ratio of the area height. The other gaps are ratios of the margin:
      - The mouth rows are separated by a thin gap (a fraction of the margin).
      - The mouth columns are separated by a gap that is a multiple of the margin.
      - The countdown slabs (and the scanner ones) are separated by exactly the margin.

    Every rectangle is given in the coordinates of the image of the area, like layout_info["relative"].
    """

    # The outer margin, as a ratio of the height of the area.
    MARGIN_RATIO: float = 0.12
    MIN_MARGIN: int = 4
    # The gap between the rows of the mouth, as a ratio of the margin. It is meant to be thin.
    ROW_GAP_RATIO: float = 0.25

    # The mouth is always this many rows: half of them above the middle, half of them below.
    MOUTH_ROWS: int = 8
    # How many rows grow above (and below) the middle for the widest column, and how many for the others.
    # Per number of columns, from left to right. The ones on the outside have less rows.
    MOUTH_COLUMNS_MAX_STEPS: dict[int, list[int]] = {
        3: [2, 4, 2],
        5: [1, 2, 4, 2, 1],
    }

    # The countdown, and the scanner that shares its shape, are this many slabs.
    SLABS: int = 8

    # How much brightness the scanner head has, and each of the slabs that follow it.
    SCANNER_BRIGHTNESS: tuple[float, ...] = (1.0, 0.5, 0.25)

    def __init__(self, area: Rectangle, mouth_columns: int = 3, mouth_column_gap_ratio: float = 2.0):
        """
        Args:
            area: The rectangle of the area, in the coordinates of its image.
            mouth_columns: 3 or 5.
            mouth_column_gap_ratio: The gap between the columns of the mouth, as a multiple of the margin.
        """
        if mouth_columns not in self.MOUTH_COLUMNS_MAX_STEPS:
            raise ValueError(f"The mouth can have {list(self.MOUTH_COLUMNS_MAX_STEPS.keys())} columns, got {mouth_columns}.")
        if mouth_column_gap_ratio < 0:
            raise ValueError(f"The gap between the columns of the mouth can't be negative, got {mouth_column_gap_ratio}.")

        self.mouth_columns: int = mouth_columns
        self.mouth_column_gap_ratio: float = mouth_column_gap_ratio

        self._x1: int = area.point_1.x
        self._y1: int = area.point_1.y
        self._width: float = area.point_2.x - area.point_1.x
        self._height: float = area.point_2.y - area.point_1.y

        self.margin: float = max(self.MIN_MARGIN, round(self._height * self.MARGIN_RATIO))

        # Calculated once: the drawing methods only read them.
        # mouth[column][row]: the bars from the top row to the bottom one.
        self.mouth: list[list[tuple[int, int, int, int]]] = self._build_mouth()
        # slabs[position]: from left to right.
        self.slabs: list[tuple[int, int, int, int]] = self._build_slabs()
        # The positions that the scanner head goes through, in order.
        self.scanner_sequence: list[int] = list(range(self.SLABS)) + list(range(self.SLABS - 2, 0, -1))

    # ---- Building the rectangles ----

    @staticmethod
    def _span(start: float, size: float, index: int, gap: float) -> tuple[int, int]:
        """
        The first and last pixel (both included, as PIL needs them) of the piece number `index` of a line of
        pieces that are `size` long, separated by `gap`, starting at `start`. The positions are rounded one by one
        from the exact value, so the rounding error does not accumulate.
        """
        begin = start + index * (size + gap)
        return round(begin), round(begin + size) - 1

    def _build_mouth(self) -> list[list[tuple[int, int, int, int]]]:
        rows = self.MOUTH_ROWS
        columns = self.mouth_columns

        row_gap = self.margin * self.ROW_GAP_RATIO
        row_height = (self._height - (2 * self.margin) - ((rows - 1) * row_gap)) / rows

        column_gap = self.margin * self.mouth_column_gap_ratio
        column_width = (self._width - (2 * self.margin) - ((columns - 1) * column_gap)) / columns

        mouth = []
        for column in range(columns):
            x1, x2 = self._span(self._x1 + self.margin, column_width, column, column_gap)
            bars = []
            for row in range(rows):
                y1, y2 = self._span(self._y1 + self.margin, row_height, row, row_gap)
                bars.append((x1, y1, x2, y2))
            mouth.append(bars)
        return mouth

    def _build_slabs(self) -> list[tuple[int, int, int, int]]:
        slabs = self.SLABS
        gap = self.margin

        slab_width = (self._width - (2 * self.margin) - ((slabs - 1) * gap)) / slabs
        y1 = round(self._y1 + self.margin)
        y2 = round(self._y1 + self._height - self.margin) - 1

        result = []
        for position in range(slabs):
            x1, x2 = self._span(self._x1 + self.margin, slab_width, position, gap)
            result.append((x1, y1, x2, y2))
        return result

    # ---- Which of them are lit ----

    def mouth_lit_bars(self, level: int, lag_per_ring: int = 0) -> list[tuple[int, int, int, int]]:
        """
        The bars of the mouth that are lit for the given level (0 is closed, 4 is wide open).
        Every column grows from the middle, up and down, up to its own maximum. The columns on the outside can go
        behind the center one: each ring, counting from the center, lags `lag_per_ring` levels more than the previous.

        Args:
            level: 0 to 4.
            lag_per_ring: 0 for all the columns moving together, 1 for each ring being one level behind.
        """
        max_steps = self.MOUTH_COLUMNS_MAX_STEPS[self.mouth_columns]
        center = self.mouth_columns // 2
        middle_above = self.MOUTH_ROWS // 2 - 1

        lit = []
        for column, bars in enumerate(self.mouth):
            ring = abs(column - center)
            steps = max(0, min(max_steps[column], level - (ring * lag_per_ring)))
            for step in range(steps):
                lit.append(bars[middle_above - step])
                lit.append(bars[middle_above + 1 + step])
        return lit

    def countdown_lit_slabs(self, percentage: float) -> list[tuple[int, int, int, int]]:
        """ The slabs that are lit for the given percentage left (0-100), from the left. """
        lit_count = math.ceil((percentage / 100) * self.SLABS)
        return self.slabs[:max(0, min(self.SLABS, lit_count))]

    def scanner_slabs(self, step: int) -> list[tuple[tuple[int, int, int, int], float]]:
        """
        The slabs that are lit for the given step of the scanner, with their brightness (0-1): the head, and the
        ones behind it, that are the positions of the steps before. If two of them are the same slab, the brightest wins.
        """
        sequence = self.scanner_sequence
        brightness_by_position: dict[int, float] = {}
        for behind, brightness in enumerate(self.SCANNER_BRIGHTNESS):
            position = sequence[(step - behind) % len(sequence)]
            brightness_by_position[position] = max(brightness, brightness_by_position.get(position, 0.0))
        # From the dimmest to the brightest, so the head is drawn the last.
        ordered = sorted(brightness_by_position.items(), key=lambda item: item[1])
        return [(self.slabs[position], brightness) for position, brightness in ordered]
