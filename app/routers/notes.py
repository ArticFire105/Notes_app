"""
Manage each student's private note for each subject.
The authenticated profile determines the owner.
The browser cannot supply a different owner.
Files are checked before OCR or storage.
Gemini transcribes the upload using the selected request key.
Only transcribed text is sent to the embedder.
Each note can contain several original pages.
Page numbers are kept for answer citations.
A database constraint enforces one note per subject.
Replacing a note must be explicitly requested.
A failed replacement preserves the previous note.
A transaction publishes the note and its chunks together.
A lock serializes replacement and deletion per subject.
Personal storage is separate from official files.
The storage path begins with the user's ID.
RLS protects both note metadata and chunks.
Backend queries also enforce the owner ID.
The backend database role bypasses RLS.
Both checks are necessary for private data.
Signed file links are returned only to the owner.
The service role key stays on the backend.
OCR and upload failures use safe error messages.
Provider diagnostics never go to the client.
Temporary OCR files are removed by the OCR module.
The original uploaded file remains private in storage.
An old object is removed after a replacement commits.
Deletion also removes searchable note chunks.
Shared answer caching must exclude personal answers.
Tests use mocked OCR and storage.
Tests must not load real configuration files.
No credentials are printed or written to logs.
The user must apply the personal-notes migration.
The frontend uses these endpoints through FastAPI.
Review transcriptions because OCR may make mistakes.
Run the offline suite with uv run pytest.
"""

from io import BytesIO
from uuid import uuid4
from threading import Lock
from time import monotonic

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pgvector import Vector
from PIL import Image
from psycopg.rows import dict_row
from pypdf import PdfReader

from app.auth import get_current_user
from app.config import Settings
from app.db import get_conn
from app.embeddings import embed_documents
from app.ingest.chunker import chunk_pages
from app.ocr import transcribe
from app.ocr import OCRFailure
from app.llm import user_api_key
from app.storage import personal_bucket

router = APIRouter(prefix="/notes", tags=["personal notes"])
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 30
_jobs = {}
_jobs_lock = Lock()
JOB_RETENTION = 3600


def has_note(user_id, subject_id):
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select exists(select 1 from personal_notes where user_id = %s and subject_id = %s)", (user_id, subject_id))
            return cursor.fetchone()[0]


@router.get("")
def my_notes(user=Depends(get_current_user)):
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""select id, subject_id, title, file_type, created_at, failed_pages from personal_notes
                              where user_id = %s order by created_at desc""", (user["id"],))
            return cursor.fetchall()


def validate_file(data, filename):
    name = filename.lower()
    if name.endswith(".pdf") and data.startswith(b"%PDF-"):
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError("PDF must have 1 to 30 unencrypted pages.")
        return ".pdf", "pdf", "application/pdf"
    if name.endswith((".png", ".jpg", ".jpeg")):
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG"} or image.width * image.height > 25000000:
                raise ValueError("Image must be a PNG or JPEG under 25 megapixels.")
            image.verify()
            suffix = ".png" if image.format == "PNG" else ".jpg"
        return suffix, "image", "image/png" if suffix == ".png" else "image/jpeg"
    raise ValueError("Upload a PDF, PNG, or JPEG image.")


def save_note(data, filename, subject_id, replace, user_id, progress=None, api_key=None):
    try:
        suffix, file_type, content_type = validate_file(data, filename)
    except Exception:
        raise HTTPException(400, "Choose a readable PDF (up to 30 pages), PNG, or JPEG image.") from None
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from subjects where id = %s", (subject_id,))
            if cursor.fetchone() is None:
                raise HTTPException(404, "Subject not found.")
    if not replace and has_note(user_id, subject_id):
        raise HTTPException(409, "You already have a note for this subject. Choose Replace to upload a new one.")
    try:
        if progress:
            progress("reading", 0)
            options = {"progress": lambda page: progress("reading", page)}
            if api_key is not None:
                options["api_key"] = api_key
            pages = transcribe(data, suffix, **options)
        else:
            pages = transcribe(data, suffix, api_key=api_key) if api_key is not None else transcribe(data, suffix)
        failed_pages = getattr(pages, "failed_pages", [])
        if failed_pages and replace:
            raise OCRFailure("Could not read pages " + ", ".join(map(str, failed_pages)) + ". Your previous note is unchanged.")
        chunks = chunk_pages(pages)
        if not chunks:
            raise ValueError("Empty transcription")
        vectors = []
        for start in range(0, len(chunks), 8):
            vectors.extend(embed_documents([item["content"] for item in chunks[start:start + 8]]))
            if progress:
                progress("indexing", len(vectors), len(chunks))
        model = Settings().embedding_model
    except OCRFailure as error:
        raise HTTPException(503, str(error)) from None
    except Exception:
        raise HTTPException(503, "Could not read or process this note. Please try again.") from None
    note_id = uuid4()
    path = f"{user_id}/{note_id}{suffix}"
    bucket = personal_bucket()
    try:
        bucket.upload(path, data, file_options={"content-type": content_type})
    except Exception:
        try:
            bucket.remove([path])
        except Exception:
            pass
        raise HTTPException(503, "Could not save the private file.") from None
    old_path = None
    old_bytes = None
    old_type = None
    remove_attempted = False
    try:
        with get_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"personal:{user_id}:{subject_id}",))
                cursor.execute("select storage_path, file_type from personal_notes where user_id = %s and subject_id = %s for update", (user_id, subject_id))
                old = cursor.fetchone()
                if old and not replace:
                    raise HTTPException(409, "You already have a note for this subject. Choose Replace to upload a new one.")
                if old:
                    old_path, old_type = old
                    old_bytes = bucket.download(old_path)
                    cursor.execute("delete from personal_notes where user_id = %s and subject_id = %s", (user_id, subject_id))
                cursor.execute("""insert into personal_notes (id, user_id, subject_id, title, storage_path, file_type, failed_pages)
                                  values (%s, %s, %s, %s, %s, %s, %s)""",
                               (note_id, user_id, subject_id, "My note", path, file_type, failed_pages))
                cursor.executemany("""insert into personal_note_chunks
                    (note_id, user_id, subject_id, page, chunk_index, content, embedding, embedding_model)
                    values (%s,%s,%s,%s,%s,%s,%s,%s)""", [
                    (note_id, user_id, subject_id, chunk["page"], chunk["chunk_index"], chunk["content"], Vector(vector), model)
                    for chunk, vector in zip(chunks, vectors, strict=True)])
                if old_path:
                    remove_attempted = True
                    bucket.remove([old_path])
    except Exception as error:
        restore_failed = False
        if remove_attempted and old_bytes is not None:
            try:
                restore_file(bucket, old_path, old_bytes, old_type)
            except Exception:
                restore_failed = True
        try:
            bucket.remove([path])
        except Exception:
            pass
        if restore_failed:
            raise HTTPException(503, "Could not restore the previous file. Contact an administrator.") from None
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, "Could not save the note. Your previous note is unchanged.") from None
    return {"id": str(note_id), "subject_id": subject_id, "title": "My note", "file_type": file_type, "failed_pages": failed_pages}


def restore_file(bucket, path, data, file_type):
    content_type = "application/pdf" if file_type == "pdf" else ("image/png" if path.endswith(".png") else "image/jpeg")
    bucket.upload(path, data, file_options={"content-type": content_type, "upsert": "true"})


def run_job(job_id, data, filename, subject_id, replace, user_id, api_key=None):
    def progress(stage, page, total=None):
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update(stage=stage, page=page, total=total, updated=monotonic())
    try:
        result = save_note(data, filename, subject_id, replace, user_id, progress=progress, **({"api_key": api_key} if api_key is not None else {}))
        with _jobs_lock:
            _jobs[job_id].update(stage="ready", result=result, updated=monotonic())
    except Exception as error:
        message = error.detail if isinstance(error, HTTPException) else "Could not process your note. Please try again."
        with _jobs_lock:
            _jobs[job_id].update(stage="failed", error=message, updated=monotonic())


@router.post("/jobs", status_code=202)
async def start_job(background_tasks: BackgroundTasks, file: UploadFile = File(),
                    subject_id: int = Form(gt=0), replace: bool = Form(default=False),
                    user=Depends(get_current_user), api_key=Depends(user_api_key)):
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Your note must be 20 MB or smaller.")
    job_id = str(uuid4())
    with _jobs_lock:
        now = monotonic()
        for key in list(_jobs):
            if _jobs[key]["stage"] in {"ready", "failed"} and now - _jobs[key]["updated"] > JOB_RETENTION:
                del _jobs[key]
        _jobs[job_id] = {"user_id": str(user["id"]), "stage": "reading", "page": 0, "updated": now}
    background_tasks.add_task(run_job, job_id, data, file.filename or "", subject_id, replace, user["id"], api_key)
    return {"id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, user=Depends(get_current_user)):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job["user_id"] != str(user["id"]):
            raise HTTPException(404, "Processing job not found. It may have expired or the server restarted.")
        return {key: value for key, value in job.items() if key not in {"user_id", "updated"}}


@router.post("")
async def upload_note(file: UploadFile = File(), subject_id: int = Form(gt=0),
                      replace: bool = Form(default=False), user=Depends(get_current_user), api_key=Depends(user_api_key)):
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Your note must be 20 MB or smaller.")
    return await run_in_threadpool(save_note, data, file.filename or "", subject_id, replace, user["id"], **({"api_key": api_key} if api_key is not None else {}))


@router.delete("/{subject_id}")
def delete_note(subject_id: int, user=Depends(get_current_user)):
    bucket = personal_bucket()
    path = None
    data = None
    file_type = None
    remove_attempted = False
    try:
        with get_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"personal:{user['id']}:{subject_id}",))
                cursor.execute("select storage_path, file_type from personal_notes where user_id = %s and subject_id = %s for update", (user["id"], subject_id))
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(404, "No personal note for this subject.")
                path, file_type = row
                data = bucket.download(path)
                cursor.execute("delete from personal_notes where user_id = %s and subject_id = %s", (user["id"], subject_id))
                remove_attempted = True
                bucket.remove([path])
    except Exception as error:
        if remove_attempted and data is not None:
            try:
                restore_file(bucket, path, data, file_type)
            except Exception:
                raise HTTPException(503, "Could not restore the note file. Contact an administrator.") from None
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, "Could not delete the note. Please try again.") from None
    return {"deleted": True}


@router.get("/{note_id}/file-url")
def note_file(note_id: str, user=Depends(get_current_user)):
    from uuid import UUID
    try:
        note_id = UUID(note_id)
    except ValueError:
        raise HTTPException(404, "Note not found.") from None
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select storage_path from personal_notes where id = %s and user_id = %s", (note_id, user["id"]))
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Note not found.")
    try:
        return {"url": personal_bucket().create_signed_url(row[0], 300)["signedURL"]}
    except Exception:
        raise HTTPException(503, "Could not open your note.") from None
