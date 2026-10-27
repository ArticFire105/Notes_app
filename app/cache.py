"""
Save successful grounded answers for repeated official-notes questions.
The ask router reads the cache before reserving paid requests.
Ingestion clears the subject cache inside its publishing transaction.
Phase 5 protects the backend Gemini allowance.
All real credentials stay outside source control.
Tests use fake settings and external service doubles.
No module creates settings while being imported.
SQL values are passed separately from SQL text.
The trusted backend owns all database writes.
RLS protects direct access through Supabase clients.
Days follow the Asia/Dubai calendar.
Cached responses do not consume questions.
BYOK requests do not consume server questions.
User keys belong only to the current request.
User keys must never appear in logs.
Authorization headers must never appear in logs.
Missing prices represent an unknown cost.
Cost estimates are not billing statements.
Output token limits also apply to BYOK.
Context token counts are approximate.
Official documents define the shared cache scope.
New ready documents invalidate subject answers.
Not-found responses are never cached.
Errors are never cached.
Sources stay beside the saved answer.
Database migrations are applied manually.
No frontend is added in this phase.
External calls are mocked in offline tests.
Use uv run pytest from the repository root.
Live Gemini checks remain manual.
Live Supabase checks remain manual.
Small helpers keep the request flow readable.
Configuration defaults can be overridden by the user.
"""

import hashlib
import json

from psycopg.types.json import Jsonb

from app.db import get_conn
from app.rag.prompt import NOT_FOUND

DOCUMENT_SET = """select coalesce(string_agg(id::text, ',' order by id), '')
                  from documents where subject_id = %s
                    and source_type = 'official' and status = 'ready'"""


def scope_version(subject_id):
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(DOCUMENT_SET, (subject_id,))
            return cursor.fetchone()[0]


def make_key(question, subject_id, module_id=None, document_id=None, version="", mode="normal"):
    normalized = " ".join(question.lower().split())
    value = [normalized, subject_id, module_id, str(document_id) if document_id else None, version, mode, "prompt-v2"]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def get(key):
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """update answer_cache set hits = hits + 1
                   where cache_key = %s returning answer, sources""", (key,),
            )
            row = cursor.fetchone()
    if row is None:
        return None
    return {"answer": row[0], "sources": row[1],
            "usage": {"input_tokens": 0, "output_tokens": 0}}


def put(key, subject_id, module_id, document_id, result):
    text = result.get("answer", "").strip()
    # Only the normal successful answer path calls this helper. Guard again so
    # no-context responses cannot become permanent cache hits.
    if (result.get("error") or result.get("detail") or not text or "not found" in text.lower()
            or text.casefold() == NOT_FOUND.casefold() or not result.get("sources")):
        return
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """insert into answer_cache
                       (cache_key, subject_id, module_id, document_id, answer, sources)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (cache_key) do nothing""",
                (key, subject_id, module_id, document_id, text, Jsonb(result["sources"])),
            )


def invalidate_scope(subject_id, cursor=None):
    # Reuse ingestion's cursor so invalidation and new notes commit together.
    if cursor is None:
        with get_conn() as connection:
            with connection.cursor() as local_cursor:
                invalidate_scope(subject_id, local_cursor)
        return
    cursor.execute("delete from answer_cache where subject_id = %s", (subject_id,))

