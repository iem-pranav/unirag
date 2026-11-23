# * Search tests: simple queries put the right document first. Needs `python -m unirag.ingest`.
import psycopg
import pytest

from unirag.db import connect
from unirag.unstructured.search import search

SIMPLE_QUERIES = [
    ("How many books can a student borrow from the library?", "06_library_guide.md"),
    ("What time does the hostel gate close?", "05_hostel_guide.md"),
    ("Who can sit for placement drives?", "11_placement_policy.md"),
]


@pytest.fixture(scope="module")
def conn():
    with connect() as c:
        yield c


@pytest.mark.parametrize("mode", ["vector", "keyword", "hybrid"])
@pytest.mark.parametrize(("query", "document"), SIMPLE_QUERIES)
def test_right_document_comes_first(
    conn: psycopg.Connection, mode: str, query: str, document: str
) -> None:
    hits = search(conn, query, mode=mode, k=3)
    assert hits[0].document == document


def test_document_filter_keeps_only_that_document(conn: psycopg.Connection) -> None:
    hits = search(conn, "fees", document="05_hostel_guide.md", k=5)
    assert hits and all(h.document == "05_hostel_guide.md" for h in hits)
