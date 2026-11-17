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
    `indent` is the nesting level (lists and quotes). When `marker` is set (a bullet or "1."),
      the block is a list item: the marker sits one level to the left of the text.
    """
    kind: str
    spans: list[Span] = field(default_factory=list)
    text: str = ""
    level: int = 0
    indent: int = 0
    marker: str | None = None


# One parser for the whole process. Created on the first use, so the import cost is not paid at startup.
_PARSER = None


def _get_parser():
    global _PARSER
    if _PARSER is None:
        from markdown_it import MarkdownIt
        # CommonMark gives us headings, lists, emphasis, inline code and code blocks.
        # Raw HTML is turned off: it is shown as text. Tables are not part of CommonMark, they stay as text too.
        _PARSER = MarkdownIt("commonmark", {"html": False, "linkify": False})
    return _PARSER


def parse_markdown(text: str) -> list[Block]:
    """
    Parses the Markdown subset that the chatbot answers use (headings, lists, bold, italic, inline code and code blocks)
    into a flat list of blocks. Everything else is kept as plain text. It never returns an empty list for a non empty text.

    Raises whatever the underlying parser raises: the callers are expected to fall back to the plain text.
    """
    tokens = _get_parser().parse(text or "")

    blocks: list[Block] = []
    list_stack: list[dict] = []     # One entry per open list: {"ordered": bool, "next": int}
    quote_depth = 0
    heading_level = 0
    pending_marker: str | None = None

    for token in tokens:
        kind = token.type

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
        else:
            line = "".join(span.text for span in block.spans)
            if block.marker is not None:
                line = ("- " if block.marker == "•" else f"{block.marker} ") + line
            lines.append(line)
    return "\n".join(lines).strip()
