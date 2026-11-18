import logging
from dataclasses import dataclass, field


@dataclass
class Span:
    """ A piece of inline text with its own style. A "\\n" in the text is a line break. """
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass
class Block:
    """
    A block of Markdown, already reduced to what the screen can show.

    kind:
      - "paragraph": spans.
      - "heading":   spans, `level` 1..6.
      - "code":      `text` as it is, in a monospaced font.
      - "rule":      a horizontal separator.
      - "table":     `rows`, each one a list of cells, each cell a list of spans. The first `header_rows` rows
                     are the header. `aligns` has "left", "center" or "right" per column.
    `indent` is the nesting level (lists and quotes). When `marker` is set (a bullet or "1."),
      the block is a list item: the marker sits one level to the left of the text.
    """
    kind: str
    spans: list[Span] = field(default_factory=list)
    text: str = ""
    level: int = 0
    indent: int = 0
    marker: str | None = None
    rows: list[list[list[Span]]] = field(default_factory=list)
    header_rows: int = 0
    aligns: list[str] = field(default_factory=list)


# One parser for the whole process. Created on the first use, so the import cost is not paid at startup.
_PARSER = None

# markdown-it logs every rule it tries on every block at DEBUG, which floods the log. INFO by default.
# Configurable in libs_logger.markdown_it.loglevel, see set_log_level().
_LOG_LEVEL: int = logging.INFO


def set_log_level(level: int):
    """ Sets the log level of the markdown-it library in this process. """
    global _LOG_LEVEL
    _LOG_LEVEL = int(level)
    logging.getLogger("markdown_it").setLevel(_LOG_LEVEL)


def _get_parser():
    global _PARSER
    if _PARSER is None:
        logging.getLogger("markdown_it").setLevel(_LOG_LEVEL)
        from markdown_it import MarkdownIt
        # CommonMark gives us headings, lists, emphasis, inline code and code blocks.
        # Raw HTML is turned off: it is shown as text. Tables are not part of CommonMark, so they are enabled apart.
        _PARSER = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
    return _PARSER


def _separate_tables(text: str) -> str:
    """
    Puts an empty line before and after every table.

    The table rule takes every following line as one more row until an empty line, so a sentence right after
    the last row ("| a | b |\\nIn short, ...") would end up inside the table. The chatbot answers do that.
    A table row is a line that starts and ends with a pipe. The lines of code blocks are left alone.
    """
    lines = text.split("\n")
    outcome: list[str] = []
    in_fence = False
    previous_is_row = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            outcome.append(line)
            previous_is_row = False
            continue

        is_row = (not in_fence) and len(stripped) > 1 and stripped.startswith("|") and stripped.endswith("|")
        if is_row != previous_is_row and stripped != "" and outcome and outcome[-1].strip() != "":
            outcome.append("")
        outcome.append(line)
        previous_is_row = is_row

    return "\n".join(outcome)


def parse_markdown(text: str) -> list[Block]:
    """
    Parses the Markdown subset that the chatbot answers use (headings, lists, bold, italic, inline code, code blocks
    and tables) into a flat list of blocks. Everything else is kept as plain text.
    It never returns an empty list for a non empty text.

    Raises whatever the underlying parser raises: the callers are expected to fall back to the plain text.
    """
    tokens = _get_parser().parse(_separate_tables(text or ""))

    blocks: list[Block] = []
    list_stack: list[dict] = []     # One entry per open list: {"ordered": bool, "next": int}
    quote_depth = 0
    heading_level = 0
    pending_marker: str | None = None
    table: dict | None = None       # The table that is being read: rows, header_rows, aligns, the open row and head flag

    for token in tokens:
        kind = token.type

        if kind == "table_open":
            table = {"rows": [], "header_rows": 0, "aligns": [], "row": None, "in_head": False}
            continue
        if table is not None:
            if kind == "thead_open":
                table["in_head"] = True
            elif kind == "thead_close":
                table["in_head"] = False
            elif kind == "tr_open":
                table["row"] = []
            elif kind in ("th_open", "td_open"):
                if not table["rows"]:
                    style = token.attrGet("style") or ""
                    table["aligns"].append("right" if "right" in style else "center" if "center" in style else "left")
            elif kind == "inline":
                table["row"].append(_inline_to_spans(token.children or []))
            elif kind == "tr_close":
                table["rows"].append(table["row"])
                if table["in_head"]:
                    table["header_rows"] += 1
            elif kind == "table_close":
                blocks.append(Block(
                    kind="table",
                    rows=table["rows"],
                    header_rows=table["header_rows"],
                    aligns=table["aligns"],
                    indent=len(list_stack) + quote_depth))
                table = None
            continue

        if kind in ("bullet_list_open", "ordered_list_open"):
            ordered = kind == "ordered_list_open"
            start = int(token.attrGet("start") or 1) if ordered else 0
            list_stack.append({"ordered": ordered, "next": start})
        elif kind in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif kind == "list_item_open":
            current_list = list_stack[-1]
            if current_list["ordered"]:
                pending_marker = f"{current_list['next']}."
                current_list["next"] += 1
            else:
                pending_marker = "•"
        elif kind == "blockquote_open":
            quote_depth += 1
        elif kind == "blockquote_close":
            quote_depth -= 1
        elif kind == "heading_open":
            heading_level = int(token.tag[1:])
        elif kind == "heading_close":
            heading_level = 0
        elif kind == "inline":
            blocks.append(Block(
                kind="heading" if heading_level > 0 else "paragraph",
                spans=_inline_to_spans(token.children or []),
                level=heading_level,
                indent=len(list_stack) + quote_depth,
                marker=pending_marker))
            # Only the first block of a list item carries the marker.
            pending_marker = None
        elif kind in ("fence", "code_block"):
            blocks.append(Block(
                kind="code",
                text=token.content.rstrip("\n"),
                indent=len(list_stack) + quote_depth))
        elif kind == "hr":
            blocks.append(Block(kind="rule", indent=len(list_stack) + quote_depth))

    return blocks


def _inline_to_spans(children) -> list[Span]:
    spans: list[Span] = []
    bold = 0
    italic = 0

    for child in children:
        kind = child.type
        if kind == "text":
            # The parser may emit empty text tokens around the emphasis marks.
            if child.content != "":
                spans.append(Span(child.content, bold > 0, italic > 0))
        elif kind == "code_inline":
            spans.append(Span(child.content, bold > 0, italic > 0, code=True))
        elif kind in ("softbreak", "hardbreak"):
            # On a screen a new line in the answer is a new line.
            spans.append(Span("\n"))
        elif kind == "strong_open":
            bold += 1
        elif kind == "strong_close":
            bold -= 1
        elif kind == "em_open":
            italic += 1
        elif kind == "em_close":
            italic -= 1
        elif kind == "image":
            spans.append(Span(child.content, bold > 0, italic > 0))
        elif kind == "html_inline":
            spans.append(Span(child.content, bold > 0, italic > 0))
        # link_open / link_close: the link text arrives as normal text spans, the URL is dropped.

    return spans


def markdown_to_plain_text(text: str) -> str:
    """
    The same text without any Markdown syntax: no emphasis marks, no heading hashes, no code fences, links reduced
    to their text. Lists keep their markers ("- " or "1.") and blocks are separated by a new line.

    Unlike a regex, a lonely "*" or "_" that does not open any emphasis (a multiplication, `snake_case`) is kept as it is.

    Raises whatever the underlying parser raises: the callers are expected to fall back to something simpler.
    """
    lines: list[str] = []
    for block in parse_markdown(text):
        if block.kind == "code":
            lines.append(block.text)
        elif block.kind == "rule":
            continue
        elif block.kind == "table":
            # A table is too wide for a narrow area: every row becomes a line of a list.
            lines.extend("- " + row for row in _table_to_rows(block, for_speech=False))
        else:
            line = "".join(span.text for span in block.spans)
            if block.marker is not None:
                line = ("- " if block.marker == "•" else f"{block.marker} ") + line
            lines.append(line)
    return "\n".join(lines).strip()


# What ends a sentence for the voice. Anything else gets a full stop, so the blocks do not run into each other.
_SENTENCE_END = ".!?:;…"


def markdown_to_speech_text(text: str, tables: str = "rows") -> str:
    """
    The text to be spoken: no Markdown syntax and no line breaks at all. Blocks (paragraphs, list items, headings,
    table rows) are joined with a space, each one ending in punctuation so the voice makes a pause.

    Args:
        text (str): The Markdown text.
        tables (str): "rows" speaks every row as a sentence ("Label: Header, value; Header, value."). "skip" leaves the tables out.

    Raises whatever the underlying parser raises: the callers are expected to fall back to something simpler.
    """
    pieces: list[str] = []
    for block in parse_markdown(text):
        if block.kind == "rule":
            continue
        if block.kind == "code":
            pieces.append(block.text)
        elif block.kind == "table":
            if tables != "skip":
                pieces.extend(_table_to_rows(block, for_speech=True))
        else:
            pieces.append("".join(span.text for span in block.spans))

    sentences: list[str] = []
    for piece in pieces:
        sentence = " ".join(piece.split())      # Also removes the line breaks inside the piece.
        if sentence == "":
            continue
        if sentence[-1] not in _SENTENCE_END:
            sentence += "."
        sentences.append(sentence)
    return " ".join(sentences).strip()


def _cell_text(cell: list[Span]) -> str:
    return " ".join("".join(span.text for span in cell).split())


def _table_to_rows(block: Block, for_speech: bool) -> list[str]:
    """
    Turns a table into one line per row, using the first column as the label of the row and the header
    as the label of every other column:
      - one column:   "value"
      - two columns:  "label: value"
      - more columns, for the screen: "label (Header: value; Header: value)"
      - more columns, for the voice:  "label: Header, value; Header, value."
    Empty cells are skipped. A table without body rows gives its header cells in one line.
    """
    # A cell that ends in a full stop would end up as "text.;" next to the separators we add.
    rows = [[_cell_text(cell).rstrip(" .;,") for cell in row] for row in block.rows]
    header = rows[:block.header_rows]
    body = rows[block.header_rows:]
    names = header[0] if header else []

    if not body:
        return [", ".join(cell for row in header for cell in row if cell)] if header else []

    lines: list[str] = []
    for row in body:
        label = row[0] if row else ""
        others = []
        for index, value in enumerate(row[1:], start=1):
            if value == "":
                continue
            name = names[index] if index < len(names) else ""
            others.append((name, value))

        if not others:
            line = label
        elif len(row) == 2:
            line = f"{label}: {others[0][1]}" if label else others[0][1]
        elif for_speech:
            parts = [f"{name}, {value}" if name else value for name, value in others]
            line = (f"{label}: " if label else "") + "; ".join(parts)
        else:
            parts = [f"{name}: {value}" if name else value for name, value in others]
            line = f"{label} ({'; '.join(parts)})" if label else "; ".join(parts)
        if line != "":
            lines.append(line)
    return lines
