"""
Expose the Phase 2 answer pipeline over HTTP.
Validate requested scope before spending model tokens.
Unknown or inconsistent scope IDs return 404.
The response contains only the answer, sources, and usage.

This module belongs to Phase 3 of the notes application.
The API wraps the existing ingestion and answering code.
It runs locally until authentication is added in Phase 4.
Do not deploy before Phase 4.

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

No authentication, quota, cache, or frontend is added here.
Run the API from the repository root.
Use uv run pytest for the offline test suite.
"""

from fastapi import APIRouter, HTTPException

from app.db import get_conn
from app.rag.answer import answer_question
from app.schemas import AskRequest, AskResponse

router = APIRouter()


def check_scope(request: AskRequest):
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from subjects where id = %s", (request.subject_id,))
            if cursor.fetchone() is None:
                raise HTTPException(404, "Subject not found.")
            if request.module_id is not None:
                cursor.execute(
                    "select id from modules where id = %s and subject_id = %s",
                    (request.module_id, request.subject_id),
                )
                if cursor.fetchone() is None:
                    raise HTTPException(404, "Module not found in this subject.")
            if request.document_id is not None:
                cursor.execute(
                    "select module_id from documents where id = %s and subject_id = %s",
                    (request.document_id, request.subject_id),
                )
                document = cursor.fetchone()
                if document is None or (
                    request.module_id is not None and document[0] != request.module_id
                ):
                    raise HTTPException(404, "Document not found in this scope.")


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    check_scope(request)
    return answer_question(
        request.question, request.subject_id, request.module_id, request.document_id
    )

