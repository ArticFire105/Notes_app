"""
List subjects and modules using the existing connection helper.
Unknown parent IDs produce a clear 404 response.
Queries return dictionary rows for response validation.
No credential or Storage metadata is selected.

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

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from app import quota
from app.auth import get_current_user
from app.db import get_conn
from app.routers.documents import DOCUMENT_COLUMNS
from app.schemas import Module, Subject

router = APIRouter()


@router.get("/subjects", response_model=list[Subject])
def list_subjects():
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select id, code, name from subjects order by code")
            return cursor.fetchall()


@router.get("/subjects/{subject_id}/modules", response_model=list[Module])
def list_modules(subject_id: int):
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select id from subjects where id = %s", (subject_id,))
            if cursor.fetchone() is None:
                raise HTTPException(404, "Subject not found.")
            cursor.execute(
                "select id, subject_id, number, title from modules where subject_id = %s order by number",
                (subject_id,),
            )
            return cursor.fetchall()



@router.get("/subjects/{subject_id}/overview")
def subject_overview(subject_id: int, user=Depends(get_current_user)):
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select id, code, name from subjects where id = %s", (subject_id,))
            subject = cursor.fetchone()
            if subject is None:
                raise HTTPException(404, "Subject not found.")
            cursor.execute("select id, subject_id, number, title from modules where subject_id = %s order by number", (subject_id,))
            modules = cursor.fetchall()
            cursor.execute("select " + DOCUMENT_COLUMNS + """, d.module_id
                           from documents d left join modules m on m.id = d.module_id
                           where d.subject_id = %s and d.source_type = 'official'
                           order by d.created_at desc""", (subject_id,))
            documents = cursor.fetchall()
    return {"subject": subject, "modules": modules, "documents": documents,
            "usage": quota.user_usage(user["id"])}
