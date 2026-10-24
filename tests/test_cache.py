"""
Test answer-cache identity, persistence, and exclusion rules offline.
Database doubles make every stored value inspectable.
Ingestion's transaction invalidation is also covered by test_ingest.
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

from unittest.mock import MagicMock

import pytest

from app import cache, config, db
from app.rag.prompt import NOT_FOUND


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External services and dotenv are forbidden in cache tests.")
    monkeypatch.setattr(config.Settings, "__init__", forbidden)
    monkeypatch.setattr(db.psycopg, "connect", forbidden)


@pytest.fixture
def database(monkeypatch):
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(cache, "get_conn", context)
    return context, cursor


def test_question_normalization():
    assert cache.make_key("  WHAT\n is   Paging? ", 1) == cache.make_key("what is paging?", 1)


@pytest.mark.parametrize("scope", [(2, None, None), (1, 12, None), (1, None, "doc")])
def test_scopes_have_different_keys(scope):
    assert cache.make_key("paging", *scope) != cache.make_key("paging", 1)


def test_ready_document_set_changes_key():
    assert cache.make_key("paging", 1, version="old-doc") != cache.make_key(
        "paging", 1, version="new-doc"
    )


def test_hit_increments_counter_and_returns_zero_usage(database):
    _, cursor = database
    sources = [{"n": 1, "page": 2}]
    cursor.fetchone.return_value = ("Paging [1]", sources)
    assert cache.get("hash") == {
        "answer": "Paging [1]", "sources": sources,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    assert "hits = hits + 1" in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1] == ("hash",)


def test_cache_miss(database):
    _, cursor = database
    cursor.fetchone.return_value = None
    assert cache.get("missing") is None


@pytest.mark.parametrize("result", [
    {"answer": NOT_FOUND, "sources": [{"page": 1}]},
    {"answer": "Not found", "sources": [{"page": 1}]},
    {"answer": "  NOT FOUND in these notes  ", "sources": [{"page": 1}]},
    {"answer": "Some answer", "sources": []},
    {"answer": "", "sources": [{"page": 1}]},
    {"error": "provider error"},
    {"answer": "Failed", "sources": [{"page": 1}], "error": "failure"},
    {"detail": "request failed"},
])
def test_not_found_and_errors_never_open_database(database, result):
    context, _ = database
    cache.put("hash", 1, None, None, result)
    context.assert_not_called()


def test_success_stores_answer_and_sources_only(database):
    _, cursor = database
    result = {"answer": "Paging [1]", "sources": [{"n": 1, "page": 2}],
              "usage": {"input_tokens": 12, "output_tokens": 3}}
    cache.put("hash", 1, 12, None, result)
    sql, values = cursor.execute.call_args.args
    assert "on conflict (cache_key) do nothing" in sql
    assert values[:5] == ("hash", 1, 12, None, "Paging [1]")
    assert values[5].obj == result["sources"]


def test_invalidate_reuses_ingest_transaction(database):
    context, cursor = database
    cache.invalidate_scope(1, cursor)
    context.assert_not_called()
    cursor.execute.assert_called_once_with(
        "delete from answer_cache where subject_id = %s", (1,)
    )


def test_scope_version_uses_only_ready_official_documents(database):
    _, cursor = database
    cursor.fetchone.return_value = ("doc-1,doc-2",)
    assert cache.scope_version(1) == "doc-1,doc-2"
    assert "source_type = 'official'" in cursor.execute.call_args.args[0]
    assert "status = 'ready'" in cursor.execute.call_args.args[0]

