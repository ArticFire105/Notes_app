"""Ingest PDF or PowerPoint text into the document and chunk tables.
Finish embedding before starting database writes to avoid partial documents.
Replace old content and insert all new rows within one database transaction.
"""

from pathlib import Path
import logging
from time import perf_counter
from uuid import UUID, uuid4

from pgvector import Vector

from app.config import Settings
from app.cache import invalidate_scope
from app.db import get_conn
from app.embeddings import EmbeddingError, embed_documents, embedding_failure_reason, prepare_embedding_text
from app.ingest.chunker import chunk_pages
from app.ingest.figures import extract_figures, describe_figure
from app.ingest.pdf_loader import load_pdf_pages
from app.ingest.pptx_loader import NO_READABLE_SLIDES, NoReadableSlidesError, load_pptx_pages
from app.logging_safety import log_safe_exception


EMBEDDING_BATCH_SIZE = 32


class IngestError(ValueError):
    """An expected ingestion failure with a message safe for the CLI to display."""

    def __init__(self, message, *, safe_reason="Document ingestion failed. Check backend logs for details."):
        super().__init__(message)
        self.safe_reason = safe_reason


def ingest_document(
    path: str | Path | bytes,
    subject_code: str,
    module_number: int,
    title: str,
    source_type: str = "official",
    replace: bool = False,
    *,
    document_id: UUID | None = None,
    file_type: str = "pdf",
    progress=None,
) -> UUID:
    started = perf_counter()
    title = title.strip()
    if not title or module_number < 1:
        raise IngestError("Provide a nonempty title and a positive module number.")
    if source_type not in {"official", "student", "past_paper"}:
        raise IngestError("source_type must be official, student, or past_paper.")

    if file_type not in {"pdf", "pptx"}:
        raise IngestError("Upload a PDF or PPTX. Save old .ppt files as .pptx first.")
    reason = "Could not load ingestion settings. Check backend configuration."
    try:
        settings = Settings()
        reason = "Could not read document text. Check that the file is valid."
        pages, skipped = load_pptx_pages(path) if file_type == "pptx" else load_pdf_pages(path)
        page_count = len(pages) + skipped
        reason = "Could not prepare document text for ingestion."
        chunks = []
        for chunk in chunk_pages(pages):
            text = prepare_embedding_text(chunk["content"])
            if text:
                chunks.append({**chunk, "content": text})
        reason = "Could not extract or describe document figures."
        figure_warning = None
        try:
            figures = extract_figures(path, file_type) if source_type == "official" else []
        except Exception as error:
            log_safe_exception(error, "Figure extraction failed; text will still be indexed if available.")
            figures = []
            figure_warning = "Some figures could not be processed; text was indexed."
        descriptions = {}
        described_figures = []
        for figure in figures:
            label = "Slide" if file_type == "pptx" else "page"
            # Repeated diagrams need separate page citations, but one description.
            if figure["data"] not in descriptions:
                try:
                    descriptions[figure["data"]] = describe_figure(figure["data"])
                except Exception as error:
                    log_safe_exception(error, "Figure description failed; skipping this figure.")
                    descriptions[figure["data"]] = None
                    figure_warning = "Some figures could not be processed; text was indexed."
            caption = descriptions[figure["data"]]
            if caption is None:
                continue
            figure["content"] = prepare_embedding_text(f"[Figure on {label} {figure['page']}]: {caption}")
            figure["id"] = uuid4()
            described_figures.append(figure)
        figures = described_figures
        if not chunks and not figures:
            if figure_warning:
                raise IngestError("Could not process figures and no readable text was available.", safe_reason="Could not process figures and no readable text was available.")
            hint = "PPTX needs readable slide text or speaker notes." if file_type == "pptx" else "Scanned PDFs need Phase 7 OCR."
            raise IngestError(
                f"No usable text: pages read={page_count}, pages skipped={skipped}, "
                f"chunks stored=0. {hint}"
            )

        reason = "Could not generate text embeddings."
        vectors = []
        all_chunks = chunks + figures
        if progress:
            progress(0, len(all_chunks))
        for start in range(0, len(all_chunks), EMBEDDING_BATCH_SIZE):
            batch = all_chunks[start:start + EMBEDDING_BATCH_SIZE]
            vectors.extend(embed_documents([chunk["content"] for chunk in batch]))
            if progress:
                progress(len(vectors), len(all_chunks))

        reason = "Could not save document text. Check database availability."
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
                        for chunk, vector in zip(chunks, vectors[:len(chunks)], strict=True)
                    ],
                )

                for index, (figure, vector) in enumerate(zip(figures, vectors[len(chunks):], strict=True)):
                    cursor.execute("insert into course_figures (id, document_id, page, image_data) values (%s,%s,%s,%s)",
                                   (figure["id"], document_id, figure["page"], figure["data"]))
                    cursor.execute("""insert into chunks
                        (document_id, subject_id, module_id, source_type, page, chunk_index, content, embedding, embedding_model, figure_id)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (document_id, subject_id, module_id, source_type, figure["page"], len(chunks) + index,
                         figure["content"], Vector(vector), settings.embedding_model, figure["id"]))

                # Publish readiness in the same transaction as the chunks.
                cursor.execute(
                    "update documents set status = 'ready', error = %s, page_count = %s where id = %s",
                    (figure_warning, page_count, document_id),
                )
                invalidate_scope(subject_id, cursor)

        # Report success only after the connection context has committed all rows.
        unit = "Slides" if file_type == "pptx" else "Pages"
        print(
            f"{unit} read: {page_count}; {unit.lower()} skipped (no usable text): {skipped}; "
            f"chunks stored: {len(chunks)}; seconds taken: {perf_counter() - started:.2f}"
        )
        return document_id
    except EmbeddingError as error:
        failure_reason = error.safe_reason
        if error.chunk_index is not None:
            chunk = batch[error.chunk_index]
            failure_reason = f"Chunk {chunk.get('chunk_index', 'figure')}: {error.safe_reason}"
            logging.getLogger("app.ingest").error(
                "Embedding failed for chunk index %s",
                chunk.get("chunk_index", "figure"),
            )
        else:
            logging.getLogger("app.ingest").error("Embedding batch failed; no individual failing chunk was reproducible.")
        log_safe_exception(error, failure_reason)
        raise IngestError(failure_reason, safe_reason=failure_reason) from error
    except NoReadableSlidesError as error:
        log_safe_exception(error, NO_READABLE_SLIDES)
        raise IngestError(NO_READABLE_SLIDES, safe_reason=NO_READABLE_SLIDES) from error
    except IngestError as error:
        log_safe_exception(error, "Document ingestion rejected.")
        raise
    except Exception as error:
        if reason == "Could not generate text embeddings.":
            reason = embedding_failure_reason(error)
        log_safe_exception(error, reason)
        raise IngestError(reason, safe_reason=reason) from error


# Keep the existing PDF CLI and imports working while uploads use the shared entry point.
ingest_pdf = ingest_document
