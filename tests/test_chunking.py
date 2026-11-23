# * Chunker tests: heading paths are set, tables are never split, long sections are split.
import re

import pytest

from unirag.ingest import load_chunks
from unirag.load_data import DOCS
from unirag.unstructured.chunking import chunk_document

TABLE = "| Item | Amount |\n|---|---|\n" + "\n".join(f"| fee {i} | {i * 100} |" for i in range(40))
DOC = f"""# Fee Rules

Intro text.

## Payment

### Late fee

Rs. 100 per day.

## Charges

Some charges:

{TABLE}

## Long section

{"First paragraph. " * 30}

{"Second paragraph. " * 30}
"""


def test_heading_path_is_metadata_and_prefix() -> None:
    chunks = {c.heading: c for c in chunk_document("fees.md", DOC, max_chars=600)}
    assert "Fee Rules > Payment > Late fee" in chunks
    late = chunks["Fee Rules > Payment > Late fee"]
    assert late.document == "fees.md"
    assert late.content.startswith("Fee Rules > Payment > Late fee\n\n")
    # * "Payment" has no text of its own, so it gets no chunk.
    assert "Fee Rules > Payment" not in chunks


def test_table_stays_whole_even_when_over_max_chars() -> None:
    assert len(TABLE) > 600
    chunks = [c for c in chunk_document("fees.md", DOC, max_chars=600) if "| fee 0 |" in c.content]
    assert len(chunks) == 1
    assert TABLE in chunks[0].content
    assert chunks[0].heading == "Fee Rules > Charges"


def test_long_section_is_split_and_each_part_keeps_heading() -> None:
    parts = [
        c for c in chunk_document("fees.md", DOC, max_chars=600) if "Long section" in c.heading
    ]
    assert len(parts) == 2
    assert all(p.content.startswith("Fee Rules > Long section\n\n") for p in parts)


@pytest.mark.parametrize("path", sorted(DOCS.glob("*.md")), ids=lambda p: p.name)
def test_every_real_table_is_inside_one_chunk(path) -> None:
    tables = re.findall(r"(?m)(?:^\|.*\n?)+", path.read_text(encoding="utf-8"))
    chunks = [c.content for c in load_chunks() if c.document == path.name]
    for table in tables:
        assert any(table.strip() in content for content in chunks)
