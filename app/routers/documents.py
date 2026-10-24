"""
Handle official PDF upload and document status polling.
The upload response is sent before embedding runs.
The background worker records safe failure messages.
Existing CLI-created documents can lack a Storage path.

This module combines Phase 3 uploads with Phase 4 permissions.
The API wraps the existing ingestion and answering code.
Every document route requires a college login.
Only administrators can upload official notes.

Database credentials stay on the backend.
The Storage service role key stays on the backend.
Responses never include configuration objects.
Raw provider errors must not reach clients or logs.

Subjects and modules define the official-notes scope.
Database IDs are distinct from module display numbers.
Uploaded PDFs live in a private notes bucket.
Signed URLs grant temporary access to one stored PDF.

Uploads are checked before background ingestion.
Document status supports polling during ingestion.
Chunks and readiness are committed together.
Background tasks are in-process rather than a durable queue.

Startup reuses the cached Phase 1 embedding model.
Question answers reuse the Phase 2 answer function.
Tests replace model loading and all external calls.
Tests never need real credentials or a real dotenv file.

Upload records use the verified administrator's profile ID.
Run the API from the repository root.
Use uv run pytest for the offline test suite.
"""

from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from psycopg.rows import dict_row
from pypdf import PdfReader

from app.db import get_conn
from app.auth import require_role
from app.ingest.pipeline import ingest_pdf
from app.schemas import DocumentOut
from app.storage import delete_pdf, signed_url, upload_pdf

router = APIRouter()
MAX_PDF_BYTES = 25 * 1024 * 1024
DOCUMENT_COLUMNS = """
    d.id, d.title, m.number as module, d.page_count, d.status, d.created_at, d.error
"""


def get_document(document_id: UUID):
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select " + DOCUMENT_COLUMNS + """, d.storage_path
                from documents d left join modules m on m.id = d.module_id
                where d.id = %s
                """,
                (document_id,),
            )
            document = cursor.fetchone()
    if document is None:
        raise HTTPException(404, "Document not found.")
    return document


def finish_upload(file_bytes, document_id, subject_code, module_number, title):
    try:
        ingest_pdf(file_bytes, subject_code, module_number, title, document_id=document_id)
    except Exception:
        # Store a fixed message: raw exceptions can contain keys or DB URLs.
        try:
            with get_conn() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "update documents set status = 'failed', error = %s where id = %s",
                        ("PDF ingestion failed; check PDF text, model access, and database setup.",
                         document_id),
                    )
        except Exception:
            # If the DB itself is unavailable, status cannot be persisted yet.
            return


@router.get("/modules/{module_id}/documents", response_model=list[DocumentOut])
def list_documents(module_id: int):
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select id from modules where id = %s", (module_id,))
            if cursor.fetchone() is None:
                raise HTTPException(404, "Module not found.")
            cursor.execute(
                "select " + DOCUMENT_COLUMNS + """
                from documents d left join modules m on m.id = d.module_id
                where d.module_id = %s and d.source_type = 'official'
                order by d.created_at desc
                """,
                (module_id,),
            )
            return cursor.fetchall()


@router.post("/documents", response_model=DocumentOut, status_code=202)
async def create_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(),
    subject_id: int = Form(gt=0),
    module_id: int = Form(gt=0),
    title: str = Form(min_length=1, max_length=500),
    user=Depends(require_role("admin")),
):
    title = title.strip()
    if not title:
        raise HTTPException(400, "Provide a nonempty document title.")
    # Read only enough to reject an oversized file before Storage or embedding.
    try:
        file_bytes = await file.read(MAX_PDF_BYTES + 1)
    finally:
        await file.close()
    if len(file_bytes) >= MAX_PDF_BYTES:
        raise HTTPException(400, "PDF must be under 25 MB.")
    if (file.content_type != "application/pdf"
            or not (file.filename or "").lower().endswith(".pdf")
            or not file_bytes.startswith(b"%PDF-")):
        raise HTTPException(400, "Upload a PDF file.")
    return await run_in_threadpool(
        queue_document, background_tasks, file_bytes, subject_id, module_id, title, user["id"]
    )


def queue_document(background_tasks, file_bytes, subject_id, module_id, title, uploaded_by):
    try:
        reader = PdfReader(BytesIO(file_bytes))
        if reader.is_encrypted or len(reader.pages) == 0:
            raise ValueError("Unreadable PDF")
    except Exception:
        raise HTTPException(400, "Upload a readable, unencrypted PDF.") from None
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select code from subjects where id = %s", (subject_id,))
            subject = cursor.fetchone()
            if subject is None:
                raise HTTPException(404, "Subject not found.")
            cursor.execute(
                "select number from modules where id = %s and subject_id = %s",
                (module_id, subject_id),
            )
            module = cursor.fetchone()
            if module is None:
                raise HTTPException(404, "Module not found in this subject.")
    document_id = uuid4()
    path = f"official/{subject['code']}/module-{module['number']}/{document_id}.pdf"
    upload_pdf(file_bytes, path)
    try:
        with get_conn() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    insert into documents
                        (id, subject_id, module_id, source_type, title, storage_path, status, uploaded_by)
                    values (%s, %s, %s, 'official', %s, %s, 'processing', %s)
                    returning id, title, page_count, status, created_at, error
                    """,
                    (document_id, subject_id, module_id, title, path, uploaded_by),
                )
                document = cursor.fetchone()
    except Exception:
        try:
            delete_pdf(path)
        except Exception:
            pass
        raise HTTPException(500, "Could not record the uploaded document.") from None
    document["module"] = module["number"]
    background_tasks.add_task(
        finish_upload, file_bytes, document_id, subject["code"], module["number"], title
    )
    return document


@router.get("/documents/{document_id}", response_model=DocumentOut)
def document_status(document_id: UUID):
    return get_document(document_id)


@router.get("/documents/{document_id}/pdf-url")
def document_pdf_url(document_id: UUID):
    document = get_document(document_id)
    if not document["storage_path"]:
        raise HTTPException(404, "This document has no stored PDF; upload it through the API.")
    return {"url": signed_url(document["storage_path"])}

