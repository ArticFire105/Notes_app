"""Ingest one local PDF into the Phase 0 document and chunk tables.
Finish embedding before starting database writes to avoid partial documents.
Replace old content and insert all new rows within one database transaction.
"""

from pathlib import Path
from time import perf_counter
from uuid import UUID

from pgvector import Vector

from app.config import Settings
from app.db import get_conn
from app.embeddings import embed_documents
from app.ingest.chunker import chunk_pages
from app.ingest.pdf_loader import load_pdf_pages


EMBEDDING_BATCH_SIZE = 32


class IngestError(ValueError):
    """An expected ingestion failure with a message safe for the CLI to display."""


def ingest_pdf(
    path: str | Path | bytes,
    subject_code: str,
    module_number: int,
    title: str,
    source_type: str = "official",
    replace: bool = False,
    *,
    document_id: UUID | None = None,
) -> UUID:
    started = perf_counter()
    title = title.strip()
    if not title or module_number < 1:
        raise IngestError("Provide a nonempty title and a positive module number.")
    if source_type not in {"official", "student", "past_paper"}:
        raise IngestError("source_type must be official, student, or past_paper.")

    settings = Settings()
    pages, skipped = load_pdf_pages(path)
    page_count = len(pages) + skipped
    chunks = chunk_pages(pages)
    if not chunks:
        raise IngestError(
            f"No usable text: pages read={page_count}, pages skipped={skipped}, "
            "chunks stored=0. Scanned PDFs need Phase 7 OCR."
        )

    vectors = []
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start:start + EMBEDDING_BATCH_SIZE]
        vectors.extend(embed_documents([chunk["content"] for chunk in batch]))

    with get_conn() as connection:
        with connection.cursor() as cursor:
            # Serialize uploads within this module so simultaneous duplicate
            # checks cannot both succeed before either document is inserted.
            cursor.execute(
                """
                select subjects.id, modules.id
                from subjects join modules on modules.subject_id = subjects.id
                where subjects.code = %s and modules.number = %s
                for update of modules
                """,
                (subject_code.strip().upper(), module_number),
            )
            scope = cursor.fetchone()
            if scope is None:
                raise IngestError("Subject/module not found; check the seed and module number.")
            subject_id, module_id = scope
            if document_id is not None:
                # The API committed this row before scheduling background ingestion.
                cursor.execute(
                    """
                    select id from documents
                    where id = %s and subject_id = %s and module_id = %s
                      and source_type = %s and status = 'processing'
                    for update
                    """,
                    (document_id, subject_id, module_id, source_type),
                )
                if cursor.fetchone() is None:
                    raise IngestError("Processing document not found in this scope.")
            else:
                cursor.execute(
                    "select id from documents where module_id = %s and title = %s",
                    (module_id, title),
                )
                if cursor.fetchone() is not None:
                    if not replace:
                        raise IngestError("A document with this module and title exists; use --replace.")
                    # Deletion stays in the insert transaction, so a failure also
                    # restores the old document and its cascade-deleted chunks.
                    cursor.execute(
                        "delete from documents where module_id = %s and title = %s",
                        (module_id, title),
                    )
                cursor.execute(
                    """
                    insert into documents
                        (subject_id, module_id, source_type, title, status, page_count)
                    values (%s, %s, %s, %s, 'ready', %s)
                    returning id
                    """,
                    (subject_id, module_id, source_type, title, page_count),
                )
                document_id = cursor.fetchone()[0]
            cursor.executemany(
                """
                insert into chunks
                    (document_id, subject_id, module_id, source_type, page,
                     chunk_index, content, embedding, embedding_model)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        document_id, subject_id, module_id, source_type,
                        chunk["page"], chunk["chunk_index"], chunk["content"],
                        Vector(vector), settings.embedding_model,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )

            # Publish readiness in the same transaction as the chunks.
            cursor.execute(
                "update documents set status = 'ready', error = null, page_count = %s where id = %s",
                (page_count, document_id),
            )

    # Report success only after the connection context has committed all rows.
    print(
        f"Pages read: {page_count}; pages skipped (no usable text): {skipped}; "
        f"chunks stored: {len(chunks)}; seconds taken: {perf_counter() - started:.2f}"
    )
    return document_id
