# * Searches doc_chunks by vector, keyword, or hybrid (reciprocal rank fusion, done in SQL).
from dataclasses import dataclass
from typing import Literal

import psycopg

from unirag.config.settings import get_settings
from unirag.unstructured.embeddings import embed, to_pgvector

Mode = Literal["vector", "keyword", "hybrid"]

DOC_FILTER = "(%(document)s::text IS NULL OR document = %(document)s)"

VECTOR_RANKS = f"""
SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS rank
FROM doc_chunks WHERE {DOC_FILTER}
ORDER BY rank LIMIT %(pool)s
"""

# * plainto_tsquery joins words with AND. Swap to OR, so one missing word doesn't drop a chunk.
KEYWORD_RANKS = f"""
SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, q.tsq) DESC) AS rank
FROM doc_chunks,
     (SELECT replace(plainto_tsquery('english', %(qtext)s)::text, '&', '|')::tsquery AS tsq) q
WHERE tsv @@ q.tsq AND {DOC_FILTER}
ORDER BY rank LIMIT %(pool)s
"""

NO_RANKS = "SELECT NULL::int AS id, NULL::bigint AS rank WHERE false"

# * RRF: score = sum of 1 / (rrf_k + rank) over the lists a chunk appears in.
FUSE = """
WITH v AS ({vector}), kw AS ({keyword})
SELECT c.document, c.heading, c.content,
       COALESCE(1.0 / (%(rrf_k)s + v.rank), 0) + COALESCE(1.0 / (%(rrf_k)s + kw.rank), 0) AS score
FROM v FULL JOIN kw USING (id) JOIN doc_chunks c USING (id)
ORDER BY score DESC, c.id
LIMIT %(k)s
"""

QUERIES: dict[str, str] = {
    "vector": FUSE.format(vector=VECTOR_RANKS, keyword=NO_RANKS),
    "keyword": FUSE.format(vector=NO_RANKS, keyword=KEYWORD_RANKS),
    "hybrid": FUSE.format(vector=VECTOR_RANKS, keyword=KEYWORD_RANKS),
}


@dataclass(frozen=True)
class Hit:
    document: str
    heading: str
    content: str
    score: float


def search(
    conn: psycopg.Connection,
    query: str,
    mode: Mode = "hybrid",
    k: int | None = None,
    document: str | None = None,
) -> list[Hit]:
    settings = get_settings()
    k = k or settings.top_k
    params = {
        "qtext": query,
        "qvec": to_pgvector(embed([query])[0]) if mode != "keyword" else None,
        "document": document,
        "pool": max(settings.candidate_pool, k),
        "rrf_k": settings.rrf_k,
        "k": k,
    }
    rows = conn.execute(QUERIES[mode], params).fetchall()
    return [Hit(*row) for row in rows]
