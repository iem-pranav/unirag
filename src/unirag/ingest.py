# * Chunks, embeds and loads data/documents into doc_chunks. Run: python -m unirag.ingest
from collections import Counter

from unirag.config.settings import get_settings
from unirag.db import connect_admin
from unirag.load_data import DOCS
from unirag.unstructured.chunking import Chunk, chunk_document
from unirag.unstructured.embeddings import embed, to_pgvector

DDL = """
CREATE TABLE doc_chunks (
    id         SERIAL PRIMARY KEY,
    document   TEXT NOT NULL,
    heading    TEXT NOT NULL,
    content    TEXT NOT NULL,
    embedding  vector({dim}) NOT NULL,
    tsv        tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX doc_chunks_tsv_idx ON doc_chunks USING gin (tsv);
CREATE INDEX doc_chunks_embedding_idx ON doc_chunks USING hnsw (embedding vector_cosine_ops);
COMMENT ON TABLE doc_chunks IS 'Chunks of the policy documents, with embeddings and keyword index.';
COMMENT ON COLUMN doc_chunks.heading IS 'Heading path, e.g. Examination Rules > Hall ticket.';
"""


def load_chunks() -> list[Chunk]:
    max_chars = get_settings().chunk_size
    return [
        chunk
        for path in sorted(DOCS.glob("*.md"))
        for chunk in chunk_document(path.name, path.read_text(encoding="utf-8"), max_chars)
    ]


def main() -> None:
    chunks = load_chunks()
    vectors = embed([c.content for c in chunks])

    with connect_admin() as conn:
        # * Drop and rebuild, so running twice gives the same table.
        conn.execute("DROP TABLE IF EXISTS doc_chunks")
        # * The vector size comes from the model, so a model change in settings can't mismatch.
        conn.execute(DDL.format(dim=int(len(vectors[0]))))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO doc_chunks (document, heading, content, embedding) "
                "VALUES (%s, %s, %s, %s::vector)",
                [
                    (c.document, c.heading, c.content, to_pgvector(v))
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
        conn.execute("GRANT SELECT ON doc_chunks TO unirag_ro")

    per_doc = Counter(c.document for c in chunks)
    print(f"Loaded {len(chunks)} chunks from {len(per_doc)} documents (dim {len(vectors[0])})")
    for document, n in sorted(per_doc.items()):
        print(f"  {document:<40} {n:>3}")


if __name__ == "__main__":
    main()
