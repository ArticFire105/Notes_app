"""
Retrieve official notes within an explicit database scope.
Question embedding reuses the Phase 1 query prompt.
The database connection reuses the Phase 1 vector adapters.
SQL returns text and the metadata needed by citations.

This file belongs only to Phase 2 of the notes application.
The phase runs through scripts before an API is introduced.
Students can scope retrieval to a subject or a module.
Document IDs can further narrow the retrieval function.
Only official notes are eligible for these searches.
Embedding model identity keeps vector comparisons compatible.
The Phase 1 embedder remains responsible for query vectors.
The Phase 1 connection helper remains responsible for transactions.
Database values are passed separately from SQL text.
Module numbers are display labels rather than database IDs.
Original page numbers connect answers to the source notes.
Numbered context blocks give the model citation targets.
Source numbers follow the order supplied to the prompt.
An unsupported question must produce the not-found response.
Empty retrieval must not trigger a paid chat request.
Chat output is limited through the existing settings class.
Usage counts are returned for later accounting work.
No quota or cache behavior is introduced in this phase.
No authentication or frontend behavior is introduced here.
Real credentials belong only in the user's local configuration.
Secrets must never appear in printed exception diagnostics.
Offline tests replace settings and external service calls.
Tests must disable dotenv loading or replace Settings entirely.
Tests do not download weights or open live database connections.
Live source-page verification remains a manual check.
The evaluation example demonstrates the input format only.
Real evaluation questions stay outside version control.
Run the scripts from the repository root with uv.
"""

from pgvector import Vector
from psycopg.rows import dict_row

from app.config import Settings
from app.db import get_conn
from app.embeddings import embed_query


def resolve_scope(subject: str, module: int | None = None) -> tuple[int, int | None]:
    # CLI module numbers are labels; retrieval needs the module's database ID.
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from subjects where code = %s", (subject.strip().upper(),))
            row = cursor.fetchone()
            if row is None:
                raise ValueError("Subject not found.")
            subject_id = row[0]
            if module is None:
                return subject_id, None
            cursor.execute(
                "select id from modules where subject_id = %s and number = %s",
                (subject_id, module),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("Module not found in this subject.")
            return subject_id, row[0]


def retrieve(question, subject_id, module_id=None, document_id=None, k=5) -> list[dict]:
    if not question.strip() or k < 1:
        raise ValueError("Provide a nonempty question and a positive k.")
    settings = Settings()
    vector = Vector(embed_query(question))
    filters = [
        "c.subject_id = %s",
        "c.source_type = 'official'",
        "c.embedding_model = %s",
    ]
    params = [vector, subject_id, settings.embedding_model]
    if module_id is not None:
        filters.append("c.module_id = %s")
        params.append(module_id)
    if document_id is not None:
        filters.append("c.document_id = %s")
        params.append(document_id)
    params.extend([vector, k])
    # Only fixed SQL fragments are joined; all supplied values stay parameters.
    query = """
        select c.content, c.page, d.title as document,
               s.code as subject, m.number as module, m.title as module_title,
               1 - (c.embedding <=> %s) as score
        from chunks c
        join documents d on d.id = c.document_id
        join subjects s on s.id = c.subject_id
        left join modules m on m.id = c.module_id
        where """ + " and ".join(filters) + """
        order by c.embedding <=> %s
        limit %s
    """
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select extversion from pg_extension where extname = 'vector'")
            version = cursor.fetchone()
            if version is not None:
                major, minor = version["extversion"].split(".")[:2]
                if (int(major), int(minor)) >= (0, 8):
                    # HNSW normally filters after scanning; keep scanning for scoped hits.
                    cursor.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            cursor.execute(query, params)
            hits = cursor.fetchall()
    # Relaxed iterative scans can return slightly unordered distances.
    return sorted(hits, key=lambda hit: hit["score"], reverse=True)

