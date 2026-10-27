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

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from app import quota, cache
from app.auth import get_current_user, require_role
from app.db import get_conn
from app.routers.documents import DOCUMENT_COLUMNS
from app.schemas import Module, Subject
from app.storage import personal_bucket, download_document, delete_document, restore_document
from app.routers.notes import restore_file

router = APIRouter()


class SubjectInput(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)


@router.post("/subjects", response_model=Subject, status_code=201)
def create_subject(request: SubjectInput, user=Depends(require_role("admin"))):
    code = request.code.strip().upper()
    name = request.name.strip()
    if not name or not re.fullmatch(r"[A-Z0-9_-]{1,20}", code):
        raise HTTPException(400, "Provide a name and a code using letters, numbers, hyphens or underscores.")
    try:
        with get_conn() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("insert into subjects (code, name) values (%s, %s) returning id, code, name", (code, name))
                subject = cursor.fetchone()
                # New subjects need modules so the existing upload flow works immediately.
                cursor.executemany("insert into modules (subject_id, number, title) values (%s, %s, %s)",
                                   [(subject["id"], number, f"Module {number}") for number in range(1, 6)])
        return subject
    except UniqueViolation:
        raise HTTPException(409, "A subject with this code already exists.") from None


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


class ModuleInput(BaseModel):
    number: int = Field(gt=0, le=999)
    title: str = Field(min_length=1, max_length=200)


class ModuleRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.post("/subjects/{subject_id}/modules", response_model=Module, status_code=201)
def create_module(subject_id: int, request: ModuleInput, user=Depends(require_role("admin"))):
    title = request.title.strip()
    if not title:
        raise HTTPException(400, "Provide a module title.")
    try:
        with get_conn() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("select id from subjects where id = %s", (subject_id,))
                if cursor.fetchone() is None:
                    raise HTTPException(404, "Subject not found.")
                cursor.execute("insert into modules (subject_id, number, title) values (%s, %s, %s) returning id, subject_id, number, title", (subject_id, request.number, title))
                return cursor.fetchone()
    except UniqueViolation:
        raise HTTPException(409, "This module number already exists.") from None


@router.put("/modules/{module_id}", response_model=Module)
def rename_module(module_id: int, request: ModuleRename, user=Depends(require_role("admin"))):
    title = request.title.strip()
    if not title:
        raise HTTPException(400, "Provide a module title.")
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("update modules set title = %s where id = %s returning id, subject_id, number, title", (title, module_id))
            module = cursor.fetchone()
            if module is None:
                raise HTTPException(404, "Module not found.")
            cache.invalidate_scope(module["subject_id"], cursor)
            return module


def remove_scope(subject_id=None, module_id=None):
    # Storage and Postgres do not share transactions. Keep backups until commit.
    attempted = []
    try:
        with get_conn() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                if module_id is not None:
                    cursor.execute("select subject_id from modules where id = %s for update", (module_id,))
                    module = cursor.fetchone()
                    if module is None:
                        raise HTTPException(404, "Module not found.")
                    subject_id = module["subject_id"]
                    cursor.execute("select storage_path from documents where module_id = %s and storage_path is not null for update", (module_id,))
                else:
                    cursor.execute("select id from subjects where id = %s for update", (subject_id,))
                    if cursor.fetchone() is None:
                        raise HTTPException(404, "Subject not found.")
                    cursor.execute("select id from modules where subject_id = %s order by id for update", (subject_id,))
                    cursor.fetchall()
                    cursor.execute("select storage_path from documents where subject_id = %s and storage_path is not null for update", (subject_id,))
                paths = [row["storage_path"] for row in cursor.fetchall()]
                backups = [("official", path, download_document(path), None) for path in paths]
                if module_id is None:
                    cursor.execute("select storage_path, file_type from personal_notes where subject_id = %s for update", (subject_id,))
                    private = cursor.fetchall()
                    if private:
                        bucket = personal_bucket()
                        backups.extend(("personal", row["storage_path"], bucket.download(row["storage_path"]), row["file_type"]) for row in private)
                if module_id is None:
                    cursor.execute("delete from personal_notes where subject_id = %s", (subject_id,))
                    cursor.execute("delete from documents where subject_id = %s", (subject_id,))
                else:
                    cursor.execute("delete from documents where module_id = %s", (module_id,))
                cache.invalidate_scope(subject_id, cursor)
                if module_id is None:
                    cursor.execute("delete from subjects where id = %s", (subject_id,))
                else:
                    cursor.execute("delete from modules where id = %s", (module_id,))
                for item in backups:
                    attempted.append(item)
                    if item[0] == "official":
                        delete_document(item[1])
                    else:
                        bucket.remove([item[1]])
    except Exception as error:
        failed = False
        for kind, path, data, file_type in attempted:
            try:
                if kind == "official":
                    restore_document(data, path)
                else:
                    restore_file(bucket, path, data, file_type)
            except Exception:
                failed = True
        if failed:
            raise HTTPException(503, "Deletion failed and some files could not be restored. Contact an administrator.") from None
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, "Could not delete this item. Please try again.") from None
    return {"deleted": True}


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, user=Depends(require_role("admin"))):
    return remove_scope(subject_id=subject_id)


@router.delete("/modules/{module_id}")
def delete_module(module_id: int, user=Depends(require_role("admin"))):
    return remove_scope(module_id=module_id)
