"""
Serve authenticated questions with Phase 5 quota and cache checks.
Validate → cache → BYOK or quota → retrieve → answer → usage → cache → remaining.
Unknown or inconsistent scope IDs return 404 before paid work.
Successful answers include sources, tokens, and the remaining allowance.

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

Authentication, quota, and caching run here; the frontend comes later.
Run the API from the repository root.
Use uv run pytest for the offline test suite.
"""

from fastapi import APIRouter, Depends, HTTPException

from app import cache, quota
from app.auth import get_current_user, check_rate_limit
from app.db import get_conn
from app.llm import user_api_key
from app.rag.answer import answer_question, answer_small_talk, is_small_talk
from app.schemas import AskRequest, AskResponse, DesignRequest
from app.rag.design import generate_design
from app.routers.notes import has_note

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
def ask(request: AskRequest, user=Depends(get_current_user), api_key=Depends(user_api_key)):
    check_rate_limit(user["id"], "chat")
    # Validate → cache → BYOK or reserve quota → retrieve → answer → usage → cache → remaining.
    check_scope(request)
    small_talk = is_small_talk(request.question)
    personal = False if small_talk else has_note(user["id"], request.subject_id)
    key = None
    # Conversations are private and context-dependent, so they never use the shared cache.
    if not request.history and not small_talk and not personal:
        version = cache.scope_version(request.subject_id)
        key = cache.make_key(request.question, request.subject_id, request.module_id,
                             request.document_id, version, request.mode)
        result = cache.get(key)
        if result is not None:
            return {**result, "remaining": quota.remaining(user["id"])}
    day = None
    if api_key is None:
        day = quota.dubai_day()
        if not quota.try_consume(user["id"], day):
            if not quota.global_ok(day=day):
                raise HTTPException(429, "Today's shared allowance or budget was reached. Add your own Google AI Studio key in Settings to keep going.")
            raise HTTPException(429, "You've used your daily questions. Add your own free Google AI Studio key in Settings to keep going.")
    if small_talk:
        result = answer_small_talk(request.question, api_key=api_key)
    else:
        options = {"mode": request.mode}
        if personal:
            options["user_id"] = user["id"]
        if api_key is not None:
            options["api_key"] = api_key
        if request.history:
            options["history"] = [turn.model_dump() for turn in request.history]
        result = answer_question(request.question, request.subject_id, request.module_id,
                                 request.document_id, **options)
    if api_key is None:
        # Rewriting a follow-up is a model call even when no notes are found.
        if (not result["sources"] and not request.history and not small_talk
                and request.mode == "strict" and not result.get("model_called", False)):
            quota.release_empty(user["id"], day)
        else:
            quota.record_usage(user["id"], **result["usage"], day=day)
    if key is not None:
        cache.put(key, request.subject_id, request.module_id, request.document_id, result)
    return {**result, "remaining": quota.remaining(user["id"])}


@router.post("/design")
def design(request: DesignRequest, user=Depends(get_current_user), api_key=Depends(user_api_key)):
    check_rate_limit(user["id"], "chat")
    check_scope(request)
    day = None
    if api_key is None:
        day = quota.dubai_day()
        if not quota.try_consume(user["id"], day):
            raise HTTPException(429, "Daily allowance reached. Add your own key in Settings or try later.")
    result = generate_design(request, user["id"], api_key)
    if api_key is None:
        if not result["model_called"]:
            quota.release_empty(user["id"], day)
        else:
            quota.record_usage(user["id"], **result["usage"], day=day)
    return {**result, "remaining": quota.remaining(user["id"])}

