# * Splits a Markdown document into chunks by headings. Each chunk starts with its heading path.
import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
BLANK_LINES = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    document: str
    heading: str
    content: str


def chunk_document(document: str, text: str, max_chars: int) -> list[Chunk]:
    return [
        Chunk(document, heading, f"{heading}\n\n{part}")
        for heading, body in sections(text)
        for part in split_blocks(body, max_chars)
    ]


def sections(text: str) -> list[tuple[str, str]]:
    # * Returns (heading path, body) pairs, e.g. ("Examination Rules > Hall ticket", "...").
    out: list[tuple[str, str]] = []
    path: list[str] = []
    lines: list[str] = []

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body and path:
            out.append((" > ".join(path), body))
        lines.clear()

    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            level = len(match[1])
            path = path[: level - 1] + [match[2].replace("**", "").strip()]
        else:
            lines.append(line)
    flush()
    return out


def split_blocks(body: str, max_chars: int) -> list[str]:
    # ! Blocks are split on blank lines only, so a table or list is never cut in half.
    # ! A single block longer than max_chars stays whole.
    parts: list[str] = []
    current = ""
    for block in BLANK_LINES.split(body):
        if current and len(current) + len(block) + 2 > max_chars:
            parts.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        parts.append(current)
    return parts
