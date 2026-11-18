import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from pitxu.lib.utils.markdown_parser import Block, parse_markdown


@dataclass
class _Segment:
    """ A run of text that is drawn with one font and one style. `x` is relative to the start of the line text. """
    text: str
    font: ImageFont.FreeTypeFont
    bold: bool = False
    italic: bool = False
    chip: bool = False      # Inline code: it gets a background chip.
    x: int = 0
    width: int = 0


@dataclass
class _Line:
    segments: list = field(default_factory=list)
    kind: str = "paragraph"         # paragraph, code, rule
    block_index: int = 0
    indent_px: int = 0
    width: int = 0                  # Width of the content, without the indent.
    ascent: int = 0
    descent: int = 0
    height: int = 0
    gap_before: int = 0
    gap_after: int = 0
    wrapped: bool = False           # This line is the continuation of a line that did not fit.
    panel: bool = False             # It belongs to a code block that gets a background panel.
    marker: str | None = None
    marker_font: ImageFont.FreeTypeFont | None = None
    marker_x: int = 0
    # Table rows. The cells of a row are segments of the same lines, placed at the x of their column.
    header: bool = False            # It belongs to the header: it gets a background.
    table_cols: list = field(default_factory=list)  # x of every vertical border, relative to the start of the line.
    row_first: bool = False         # First line of a row: the border above is drawn here.
    table_end: bool = False         # Last line of the table: the border below is drawn here.
    pad_top: int = 0                # Space inside the row, above and below the text. It is inside the borders.
    pad_bottom: int = 0


class MarkdownRenderer:
    """
    Draws a small subset of Markdown (headings, lists, bold, italic, inline code, code blocks) with PIL,
    fitting the biggest font of the ladder that holds the whole text, and truncating with "…" when not even the smallest does.

    The fonts we have are regular ones, so:
      - Bold is faked drawing the text twice, 1 px apart.
      - Italic is faked drawing the text into a mask and shearing it.
      - Code uses the monospaced face of a font file, if given.
    If better fonts come later, the changes are in _text_width() and _draw_segment().

    It only knows about drawing. Parsing is in pitxu.lib.utils.markdown_parser.
    """

    BOLD_OFFSET_PX: int = 1
    ITALIC_SHEAR: float = 0.2
    LINE_SPACING_PX: int = 2
    # Space between blocks, as a share of the height of a line. Items of the same list are tight.
    BLOCK_GAP_RATIO: float = 0.4
    HEADING_GAP_RATIO: float = 0.7
    CHIP_PAD_X: int = 3
    CELL_PAD_X: int = 5
    CELL_PAD_Y: int = 2
    PANEL_PAD: int = 6
    PANEL_RADIUS: int = 6
    ELLIPSIS: str = "…"
    # Backgrounds for the code, per color mode. Opaque on purpose: ImageDraw does not blend translucent colors.
    # No entry for a mode (like "1") means no background.
    CHIP_COLORS: dict = {"RGBA": (200, 200, 200, 255), "RGB": (200, 200, 200), "L": 200}
    PANEL_COLORS: dict = {"RGBA": (214, 214, 214, 255), "RGB": (214, 214, 214), "L": 214}

    def __init__(self, fonts: list, mono_font_file: str | None = None, mono_font_index: int = 0,
                 color_mode: str = "RGBA"):
        """
        Args:
            fonts (list): The ladder of fonts to try, in any order (they are sorted by size).
            mono_font_file (str): Font file for the code. Falls back to the regular font if it can not be loaded.
            mono_font_index (int): Face inside the file, for collections.
            color_mode (str): The mode of the image that we draw on. It defines the backgrounds for the code.
        """
        by_size: dict[int, ImageFont.FreeTypeFont] = {}
        for font in fonts:
            by_size.setdefault(int(font.size), font)
        self._ladder: list = [by_size[size] for size in sorted(by_size)]
        if not self._ladder:
            raise ValueError("MarkdownRenderer needs at least one font")

        self._mono_file = mono_font_file
        self._mono_index = mono_font_index
        self._mono_cache: dict[int, ImageFont.FreeTypeFont] = {}
        self._color_mode = str(color_mode)

    # ------------------------- Public -------------------------

    def draw(self, draw: ImageDraw.ImageDraw, text: str, box: tuple, text_color, center: bool = True) -> bool:
        """
        Draws the Markdown text inside the box (x0, y0, x1, y1).
        Returns False, drawing nothing, when there is nothing to draw. Raises when the parsing or the drawing fail.
        """
        blocks = parse_markdown(text)
        if not blocks:
            return False
        self._draw_blocks(draw, blocks, box, text_color, center, panel=True, prefer_no_wrap=False)
        return True

    def draw_code(self, draw: ImageDraw.ImageDraw, code: str, box: tuple, text_color, center: bool = True) -> bool:
        """
        Draws a piece of code, as it comes, in the monospaced font.
        It prefers a smaller font over wrapping the lines. The background is up to the caller.
        """
        if code is None or code.strip() == "":
            return False
        self._draw_blocks(draw, [Block(kind="code", text=code)], box, text_color, center, panel=False, prefer_no_wrap=True)
        return True

    # ------------------------- Fonts -------------------------

    def _mono_for(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._mono_cache:
            font = None
            if self._mono_file:
                try:
                    font = ImageFont.truetype(self._mono_file, size, index=self._mono_index)
                except Exception:
                    font = None
            if font is None:
                # The ladder font with the closest size.
                font = min(self._ladder, key=lambda candidate: abs(int(candidate.size) - size))
            self._mono_cache[size] = font
        return self._mono_cache[size]

    def _text_width(self, text: str, font: ImageFont.FreeTypeFont, bold: bool) -> int:
        # Rounded, not ceiled: the error of every measure adds up along a line, and it shows as wider gaps between styles.
        return round(font.getlength(text)) + (self.BOLD_OFFSET_PX if bold else 0)

    @staticmethod
    def _font_height(font: ImageFont.FreeTypeFont) -> tuple[int, int]:
        ascent, descent = font.getmetrics()
        return int(ascent), int(descent)

    # ------------------------- Layout -------------------------

    def _layout(self, blocks: list, font_index: int, max_width: int, panel: bool) -> tuple[list, bool]:
        """ Turns the blocks into lines for the given font of the ladder. Returns the lines and if any line had to wrap. """
        base_font = self._ladder[font_index]
        heading_font = self._ladder[min(font_index + 1, len(self._ladder) - 1)]
        mono_font = self._mono_for(int(base_font.size))

        ascent, descent = self._font_height(base_font)
        base_line_height = ascent + descent + self.LINE_SPACING_PX
        indent_step = max(20, int(base_font.size * 1.2))

        lines: list[_Line] = []
        any_wrapped = False

        for index, block in enumerate(blocks):
            previous = blocks[index - 1] if index > 0 else None

            # Space before the block
            if previous is None:
                gap = 0
            elif previous.marker is not None and block.marker is not None:
                gap = 0
            else:
                ratio = self.HEADING_GAP_RATIO if block.kind == "heading" else self.BLOCK_GAP_RATIO
                gap = int(base_line_height * ratio)

            indent_px = block.indent * indent_step
            marker_x = 0
            if block.marker is not None:
                marker_x = max(0, block.indent - 1) * indent_step
                marker_width = self._text_width(block.marker, base_font, False)
                indent_px = max(indent_px, marker_x + marker_width + 8)

            if block.kind == "rule":
                line = _Line(kind="rule", block_index=index, indent_px=indent_px,
                             width=max_width - indent_px,
                             height=base_line_height // 2, gap_before=gap)
                lines.append(line)
                continue

            if block.kind == "code":
                block_lines = self._layout_code(block, mono_font, max_width - indent_px, indent_px, index, panel)
            elif block.kind == "table":
                block_lines = self._layout_table(block, base_font, mono_font, max_width - indent_px, indent_px, index)
            else:
                font = heading_font if block.kind == "heading" and block.level <= 2 else base_font
                block_lines = self._layout_inline(block, font, mono_font, max_width - indent_px, indent_px, index)

            if block.marker is not None and block_lines:
                block_lines[0].marker = block.marker
                block_lines[0].marker_font = base_font
                block_lines[0].marker_x = marker_x

            if block_lines:
                block_lines[0].gap_before += gap
                any_wrapped = any_wrapped or any(line.wrapped for line in block_lines)
                lines.extend(block_lines)

        return lines, any_wrapped

    def _layout_inline(self, block: Block, font: ImageFont.FreeTypeFont, mono_font: ImageFont.FreeTypeFont,
                       avail_width: int, indent_px: int, block_index: int) -> list:
        """ Wraps the spans of a paragraph or heading into lines. """
        force_bold = block.kind == "heading"
        base_ascent, base_descent = self._font_height(font)

        lines: list[_Line] = []

        def new_line(wrapped: bool) -> _Line:
            line = _Line(kind="paragraph", block_index=block_index, indent_px=indent_px, wrapped=wrapped)
            lines.append(line)
            return line

        current = new_line(False)

        def append(text: str, seg_font: ImageFont.FreeTypeFont, bold: bool, italic: bool, chip: bool):
            """ Adds text to the current line, merging it with the last segment when the style is the same. """
            last = current.segments[-1] if current.segments else None
            if last is not None and last.font is seg_font and last.bold == bold and last.italic == italic and last.chip == chip:
                # The merged text is measured as a whole, the same way it is drawn: summing the measures of its
                #   pieces drifts, and the next segment would start in the wrong place.
                last.text += text
                merged_width = self._text_width(last.text, seg_font, bold)
                current.width += merged_width - last.width
                last.width = merged_width
            else:
                width = self._text_width(text, seg_font, bold)
                pad = self.CHIP_PAD_X if chip else 0
                current.segments.append(_Segment(text, seg_font, bold, italic, chip, x=current.width + pad, width=width))
                # The chip reserves its padding on both sides at once.
                current.width += width + 2 * pad
            ascent, descent = self._font_height(seg_font)
            current.ascent = max(current.ascent, ascent)
            current.descent = max(current.descent, descent)

        for span in block.spans:
            seg_font = mono_font if span.code else font
            bold = span.bold or force_bold
            chip = span.code

            for part_index, part in enumerate(span.text.split("\n")):
                if part_index > 0:
                    current = new_line(False)

                for token in re.findall(r"\S+|\s+", part):
                    is_space = token.isspace()
                    width = self._text_width(token, seg_font, bold)
                    # A chip that starts in this line pays its padding.
                    starts_chip = chip and not (current.segments and current.segments[-1].chip and current.segments[-1].font is seg_font)
                    extra = 2 * self.CHIP_PAD_X if starts_chip else 0

                    if current.width + width + extra <= avail_width:
                        if is_space and not current.segments:
                            continue    # No leading spaces in a line.
                        append(token, seg_font, bold, span.italic, chip)
                        continue

                    # It does not fit.
                    if is_space:
                        current = new_line(True)    # The space is dropped at the wrapping point.
                        continue
                    if current.segments:
                        current = new_line(True)
                        starts_chip = chip
                        extra = 2 * self.CHIP_PAD_X if starts_chip else 0
                    if width + extra <= avail_width:
                        append(token, seg_font, bold, span.italic, chip)
                        continue

                    # A word longer than the whole line: cut it where it fits.
                    chunk = ""
                    for char in token:
                        if chunk and self._text_width(chunk + char, seg_font, bold) + extra > avail_width:
                            append(chunk, seg_font, bold, span.italic, chip)
                            current = new_line(True)
                            chunk = ""
                            extra = 2 * self.CHIP_PAD_X if chip else 0
                        chunk += char
                    if chunk:
                        append(chunk, seg_font, bold, span.italic, chip)

        # An empty last line (the text ended with a line break) is noise.
        while len(lines) > 1 and not lines[-1].segments:
            lines.pop()

        for line in lines:
            if not line.segments:
                line.ascent, line.descent = base_ascent, base_descent
            line.height = line.ascent + line.descent + self.LINE_SPACING_PX
            # Trailing spaces do not count.
            if line.segments and line.segments[-1].text.endswith(" "):
                last = line.segments[-1]
                stripped = last.text.rstrip()
                removed = last.width - self._text_width(stripped, last.font, last.bold) if stripped else last.width
                if stripped:
                    last.text = stripped
                    last.width -= removed
                    line.width -= removed
                else:
                    line.segments.pop()
                    line.width -= removed
        return lines

    def _layout_table(self, block: Block, font: ImageFont.FreeTypeFont, mono_font: ImageFont.FreeTypeFont,
                      avail_width: int, indent_px: int, block_index: int) -> list:
        """
        A table keeps its grid. The columns take the width of their widest cell. If that does not fit, they are
        narrowed in proportion to what they have to give (never below their longest word), and their cells wrap.
        """
        rows = [row for row in block.rows if row]
        if not rows:
            return []
        columns = max(len(row) for row in rows)
        rows = [row + [[] for _ in range(columns - len(row))] for row in rows]
        aligns = (list(block.aligns) + ["left"] * columns)[:columns]
        pad_x, pad_y = self.CELL_PAD_X, self.CELL_PAD_Y

        def cell_block(cell: list, header: bool) -> Block:
            # The header is drawn like a heading: bold. The font is the one that we give, whatever the level.
            return Block(kind="heading" if header else "paragraph", spans=cell)

        # What every column wants (all its cells in one line) and the least it accepts (its longest word).
        natural = [0] * columns
        minimum = [0] * columns
        for row_index, row in enumerate(rows):
            header = row_index < block.header_rows
            for column, cell in enumerate(row):
                cell_width = 0
                for span in cell:
                    span_font = mono_font if span.code else font
                    bold = span.bold or header
                    chip = 2 * self.CHIP_PAD_X if span.code else 0
                    cell_width += self._text_width(span.text.replace("\n", " "), span_font, bold) + chip
                    for word in span.text.split():
                        minimum[column] = max(minimum[column], self._text_width(word, span_font, bold) + chip)
                natural[column] = max(natural[column], cell_width)
        minimum = [min(least, wanted) for least, wanted in zip(minimum, natural)]

        overhead = columns * 2 * pad_x + (columns + 1)
        room = avail_width - overhead
        if room <= columns:
            widths = [1] * columns
        elif sum(natural) <= room:
            widths = natural
        elif sum(minimum) >= room:
            # Not even the longest words fit: they will be cut.
            widths = [max(1, int(least * room / sum(minimum))) for least in minimum]
        else:
            spare = room - sum(minimum)
            can_give = [wanted - least for wanted, least in zip(natural, minimum)]
            widths = [least + int(spare * give / sum(can_give)) for least, give in zip(minimum, can_give)]

        # The vertical borders, and the end of the table.
        borders = [0]
        for width in widths:
            borders.append(borders[-1] + 1 + 2 * pad_x + width)
        total_width = borders[-1] + 1

        base_ascent, base_descent = self._font_height(font)
        lines: list[_Line] = []
        for row_index, row in enumerate(rows):
            header = row_index < block.header_rows
            cells = [
                self._layout_inline(cell_block(cell, header), font, mono_font, widths[column], 0, block_index)
                for column, cell in enumerate(row)]

            row_lines: list[_Line] = []
            for line_index in range(max(len(cell_lines) for cell_lines in cells)):
                line = _Line(kind="table", block_index=block_index, indent_px=indent_px, width=total_width,
                             header=header, table_cols=borders)
                ascent = descent = 0
                for column, cell_lines in enumerate(cells):
                    if line_index >= len(cell_lines):
                        continue
                    cell_line = cell_lines[line_index]
                    shift = borders[column] + 1 + pad_x
                    if aligns[column] == "right":
                        shift += widths[column] - cell_line.width
                    elif aligns[column] == "center":
                        shift += (widths[column] - cell_line.width) // 2
                    for segment in cell_line.segments:
                        segment.x += shift
                        line.segments.append(segment)
                    ascent = max(ascent, cell_line.ascent)
                    descent = max(descent, cell_line.descent)
                line.ascent = ascent or base_ascent
                line.descent = descent or base_descent
                line.height = line.ascent + line.descent + self.LINE_SPACING_PX
                row_lines.append(line)

            row_lines[0].row_first = True
            row_lines[0].pad_top = pad_y
            row_lines[0].gap_before += pad_y
            row_lines[-1].pad_bottom = pad_y
            row_lines[-1].gap_after += pad_y
            lines.extend(row_lines)

        lines[-1].table_end = True
        return lines

    def _layout_code(self, block: Block, font: ImageFont.FreeTypeFont, avail_width: int, indent_px: int,
                     block_index: int, panel: bool) -> list:
        """ A code block keeps its lines. Only the lines that do not fit are cut where they fit. """
        pad = self.PANEL_PAD if panel else 0
        text_width_limit = avail_width - 2 * pad
        ascent, descent = self._font_height(font)

        lines: list[_Line] = []
        for raw_line in block.text.replace("\t", "    ").split("\n"):
            chunks: list[str] = []
            chunk = ""
            for char in raw_line:
                if chunk and self._text_width(chunk + char, font, False) > text_width_limit:
                    chunks.append(chunk)
                    chunk = ""
                chunk += char
            chunks.append(chunk)

            for chunk_index, text in enumerate(chunks):
                width = self._text_width(text, font, False) if text else 0
                lines.append(_Line(
                    segments=[_Segment(text, font, x=0, width=width)] if text else [],
                    kind="code", block_index=block_index, indent_px=indent_px + pad, width=width,
                    ascent=ascent, descent=descent, height=ascent + descent + self.LINE_SPACING_PX,
                    wrapped=chunk_index > 0, panel=panel))

        if panel and lines:
            lines[0].gap_before += pad
            lines[-1].gap_after += pad
        return lines

    @staticmethod
    def _total_height(lines: list) -> int:
        return sum(line.gap_before + line.height + line.gap_after for line in lines)

    # ------------------------- Fit -------------------------

    def _fit(self, blocks: list, max_width: int, max_height: int, panel: bool, prefer_no_wrap: bool) -> list:
        """
        Picks the biggest font that holds all the text. If none does, takes the smallest and truncates.
        With prefer_no_wrap, a smaller font that does not wrap any line wins over a bigger one that does.
        """
        wrapped_fallback = None
        for font_index in reversed(range(len(self._ladder))):
            lines, any_wrapped = self._layout(blocks, font_index, max_width, panel)
            if self._total_height(lines) > max_height:
                continue
            if prefer_no_wrap and any_wrapped:
                if wrapped_fallback is None:
                    wrapped_fallback = lines
                continue
            return lines
        if wrapped_fallback is not None:
            return wrapped_fallback

        lines, _ = self._layout(blocks, 0, max_width, panel)
        return self._truncate(lines, max_width, max_height)

    def _truncate(self, lines: list, max_width: int, max_height: int) -> list:
        """ Keeps the lines that fit and ends the last one with an ellipsis. """
        kept: list[_Line] = []
        used = 0
        for line in lines:
            needed = line.gap_before + line.height + line.gap_after
            if kept and used + needed > max_height:
                break
            kept.append(line)
            used += needed
        if len(kept) < len(lines):
            self._ellipsize(kept[-1], max_width)
            if kept[-1].kind == "table":
                # The table is cut here: the grid is closed at this line.
                kept[-1].table_end = True
        return kept

    def _ellipsize(self, line: _Line, max_width: int):
        """ Shortens the line, at the end, until the ellipsis fits. """
        line_limit = max_width - line.indent_px
        while line.segments:
            segment = line.segments[-1]
            limit = line_limit
            if line.kind == "table":
                # In a table the ellipsis has to stay inside the cell: before the next border of its column.
                next_borders = [border for border in line.table_cols if border > segment.x]
                if next_borders:
                    limit = min(next_borders) - self.CELL_PAD_X - 1
            text = segment.text.rstrip()
            while text:
                candidate = text + self.ELLIPSIS
                width = self._text_width(candidate, segment.font, segment.bold)
                if segment.x + width <= limit:
                    segment.text = candidate
                    segment.width = width
                    if line.kind != "table":
                        # A table line keeps the width of the table.
                        line.width = segment.x + width
                    return
                text = text[:-1].rstrip()
            line.segments.pop()
        # Nothing was left in the line, the ellipsis goes alone.
        font = self._ladder[0]
        width = self._text_width(self.ELLIPSIS, font, False)
        if line.kind == "table":
            line.segments = [_Segment(self.ELLIPSIS, font, x=1 + self.CELL_PAD_X, width=width)]
            return
        line.segments = [_Segment(self.ELLIPSIS, font, x=0, width=width)]
        line.width = width
        line.ascent, line.descent = self._font_height(font)
        line.height = line.ascent + line.descent + self.LINE_SPACING_PX

    # ------------------------- Draw -------------------------

    def _draw_blocks(self, draw: ImageDraw.ImageDraw, blocks: list, box: tuple, text_color,
                     center: bool, panel: bool, prefer_no_wrap: bool):
        x0, y0, x1, y1 = box
        width = int(x1 - x0)
        height = int(y1 - y0)

        lines = self._fit(blocks, width, height, panel, prefer_no_wrap)
        if not lines:
            return

        total_height = self._total_height(lines)
        block_width = max(
            line.indent_px + line.width + (self.PANEL_PAD if line.panel else 0)
            for line in lines)

        offset_x = x0 + ((width - block_width) // 2 if center and block_width < width else 0)
        offset_y = y0 + ((height - total_height) // 2 if center and total_height < height else 0)

        # Where every line starts.
        tops: list[int] = []
        y = offset_y
        for line in lines:
            y += line.gap_before
            tops.append(y)
            y += line.height + line.gap_after

        self._draw_panels(draw, lines, tops, offset_x)

        for line, top in zip(lines, tops):
            line_x = offset_x + line.indent_px
            baseline = top + line.ascent

            if line.kind == "rule":
                middle = top + line.height // 2
                draw.line([(line_x, middle), (line_x + line.width, middle)], fill=text_color, width=1)
                continue

            if line.marker is not None and line.marker_font is not None:
                draw.text((offset_x + line.marker_x, baseline), line.marker, font=line.marker_font,
                          fill=text_color, anchor="ls")

            if line.kind == "table" and line.header:
                self._draw_table_header_background(draw, line, line_x, top)

            for segment in line.segments:
                segment_x = line_x + segment.x
                if segment.chip:
                    self._draw_chip(draw, segment_x - self.CHIP_PAD_X, top, segment_x + segment.width + self.CHIP_PAD_X, top + line.height)
                self._draw_segment(draw, segment_x, baseline, segment, text_color)

            if line.kind == "table":
                self._draw_table_borders(draw, line, line_x, top, text_color)

    def _draw_table_header_background(self, draw: ImageDraw.ImageDraw, line: _Line, line_x: int, top: int):
        color = self.CHIP_COLORS.get(self._color_mode)
        if color is None:
            return
        draw.rectangle(
            (line_x, top - line.pad_top, line_x + line.width - 1, top + line.height + line.pad_bottom - 1),
            fill=color)

    @staticmethod
    def _draw_table_borders(draw: ImageDraw.ImageDraw, line: _Line, line_x: int, top: int, color):
        """ The part of the grid that belongs to this line: its vertical borders, and the horizontal ones at the edges of the row. """
        y_top = top - line.pad_top
        y_bottom = top + line.height + line.pad_bottom
        for x in line.table_cols:
            draw.line([(line_x + x, y_top), (line_x + x, y_bottom)], fill=color, width=1)
        if line.row_first:
            draw.line([(line_x, y_top), (line_x + line.width - 1, y_top)], fill=color, width=1)
        if line.table_end:
            draw.line([(line_x, y_bottom), (line_x + line.width - 1, y_bottom)], fill=color, width=1)

    def _draw_panels(self, draw: ImageDraw.ImageDraw, lines: list, tops: list, offset_x: int):
        """ One background per code block, as wide as its widest line. """
        color = self.PANEL_COLORS.get(self._color_mode)
        if color is None:
            return

        index = 0
        while index < len(lines):
            if not lines[index].panel:
                index += 1
                continue
            end = index
            while end + 1 < len(lines) and lines[end + 1].panel and lines[end + 1].block_index == lines[index].block_index:
                end += 1

            group = lines[index:end + 1]
            left = offset_x + group[0].indent_px - self.PANEL_PAD
            right = offset_x + max(line.indent_px + line.width for line in group) + self.PANEL_PAD
            top = tops[index] - self.PANEL_PAD
            bottom = tops[end] + group[-1].height + self.PANEL_PAD
            draw.rounded_rectangle((left, top, right, bottom), radius=self.PANEL_RADIUS, fill=color)
            index = end + 1

    def _draw_chip(self, draw: ImageDraw.ImageDraw, left: int, top: int, right: int, bottom: int):
        color = self.CHIP_COLORS.get(self._color_mode)
        if color is None:
            return
        draw.rounded_rectangle((left, top, right, bottom), radius=3, fill=color)

    def _draw_segment(self, draw: ImageDraw.ImageDraw, x: int, baseline: int, segment: _Segment, color):
        if not segment.text:
            return

        if not segment.italic:
            draw.text((x, baseline), segment.text, font=segment.font, fill=color, anchor="ls")
            if segment.bold:
                draw.text((x + self.BOLD_OFFSET_PX, baseline), segment.text, font=segment.font, fill=color, anchor="ls")
            return

        # Faux italic: the text goes into a mask, the mask is sheared around the baseline, and painted with the color.
        ascent, descent = self._font_height(segment.font)
        mask_height = ascent + descent + 2
        pad = int(mask_height * self.ITALIC_SHEAR) + 2
        mask = Image.new("L", (segment.width + 2 * pad, mask_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.text((pad, ascent), segment.text, font=segment.font, fill=255, anchor="ls")
        if segment.bold:
            mask_draw.text((pad + self.BOLD_OFFSET_PX, ascent), segment.text, font=segment.font, fill=255, anchor="ls")
        mask = mask.transform(
            mask.size, Image.AFFINE,
            (1, self.ITALIC_SHEAR, -self.ITALIC_SHEAR * ascent, 0, 1, 0),
            resample=Image.BILINEAR)
        draw.bitmap((x - pad, baseline - ascent), mask, fill=color)
