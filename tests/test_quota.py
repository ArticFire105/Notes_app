"""
Test quota SQL, request routing, and BYOK protection without services.
HTTP tests override authentication and inspect all accounting calls.
Model and database doubles prevent reading any real configuration.
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

from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app import cache, config, db, llm, main, quota
from app.auth import get_current_user
from app.rag import answer
from app.rag.prompt import NOT_FOUND
from app.routers import ask

DAY = date(2026, 10, 24)
USER = {"id": "00000000-0000-0000-0000-000000000001",
        "email": "student@dxb.manipal.edu", "role": "student"}
RESULT = {"answer": "Paging [1]",
          "sources": [{"n": 1, "document": "Memory", "module": 2, "page": 14, "score": 0.9}],
          "usage": {"input_tokens": 20, "output_tokens": 5}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not load dotenv or external services.")
    monkeypatch.setattr(config.Settings, "__init__", forbidden)
    monkeypatch.setattr(db.psycopg, "connect", forbidden)
    monkeypatch.setattr(llm, "init_chat_model", forbidden)
    monkeypatch.setattr(main, "get_embedder", lambda: None)


@pytest.fixture
def settings(monkeypatch):
    values = SimpleNamespace(
        questions_per_day=5, global_daily_cap=100, global_daily_budget_usd=None,
        price_input_per_1m_usd=Decimal("0"), price_output_per_1m_usd=Decimal("0"),
    )
    monkeypatch.setattr(quota, "Settings", lambda: values)
    return values


@pytest.fixture
def database(monkeypatch, settings):
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(quota, "get_conn", context)
    return cursor


def test_reserve_uses_lock_and_atomic_limit(database):
    database.fetchone.side_effect = [(4, 0, 0, Decimal(0)), (5,)]
    assert quota.try_consume(USER["id"], DAY)
    calls = database.execute.call_args_list
    assert "pg_advisory_xact_lock" in calls[0].args[0]
    assert "sum(requests)" in calls[1].args[0]
    sql, values = calls[2].args
    assert "on conflict (user_id, day) do update" in sql
    assert "where usage_daily.requests < %s" in sql
    assert "returning requests" in sql
    assert values == (USER["id"], DAY, 5)


def test_sixth_reservation_returns_false(database):
    database.fetchone.side_effect = [(5, 0, 0, Decimal(0)), None]
    assert not quota.try_consume(USER["id"], DAY)


def test_global_cap_prevents_reservation(database, settings):
    settings.global_daily_cap = 1
    database.fetchone.return_value = (1, 0, 0, Decimal(0))
    assert not quota.try_consume(USER["id"], DAY)
    assert not any("insert into" in call.args[0] for call in database.execute.call_args_list)


@pytest.mark.parametrize("spent,expected", [("0.99", True), ("1.00", False)])
def test_budget_boundary(database, settings, spent, expected):
    settings.global_daily_budget_usd = Decimal("1")
    settings.price_input_per_1m_usd = settings.price_output_per_1m_usd = Decimal("1")
    database.fetchone.return_value = (0, 0, 0, Decimal(spent))
    assert quota.global_ok() is expected


def test_budget_with_unknown_prices_blocks_server_key(database, settings):
    settings.global_daily_budget_usd = Decimal("1")
    database.fetchone.return_value = (0, 0, 0, Decimal(0))
    assert quota.global_ok() is False


def test_unknown_cost_and_decimal_calculation(settings):
    assert quota.estimate_cost(100, 20) is None
    settings.price_input_per_1m_usd = Decimal("0.1")
    assert quota.estimate_cost(100, 20) is None
    settings.price_output_per_1m_usd = Decimal("0.4")
    assert quota.estimate_cost(100, 20) == Decimal("0.000018")


def test_record_uses_reserved_day_even_after_midnight(database, settings):
    settings.price_input_per_1m_usd = Decimal("0.1")
    settings.price_output_per_1m_usd = Decimal("0.4")
    quota.record_usage(USER["id"], 100, 20, DAY)
    sql, values = database.execute.call_args.args
    assert "input_tokens = input_tokens + %s" in sql
    assert values == (100, 20, Decimal("0.000018"), USER["id"], DAY)


def test_dubai_day_and_remaining(database):
    database.fetchone.return_value = (DAY,)
    assert quota.dubai_day() == DAY
    assert "now() at time zone 'Asia/Dubai'" in database.execute.call_args.args[0]
    reset = datetime(2026, 10, 24, 20, tzinfo=timezone.utc)
    database.fetchone.return_value = (5, reset)
    assert quota.user_usage(USER["id"]) == {"used": 5, "limit": 5, "resets_at": reset}
    assert quota.remaining(USER["id"]) == 0


def test_admin_spend_unknown(database):
    database.fetchone.return_value = (3, 100, 20, Decimal(0))
    assert quota.admin_usage()["est_cost_usd"] == "unknown"


@pytest.fixture
def api(monkeypatch):
    mocks = SimpleNamespace(
        reserve=MagicMock(return_value=True), record=MagicMock(),
        remaining=MagicMock(return_value=4), release=MagicMock(),
        cached=MagicMock(return_value=None), put=MagicMock(),
        generate=MagicMock(return_value=RESULT), global_ok=MagicMock(return_value=True),
        status=MagicMock(return_value={"used": 1, "limit": 5, "resets_at": "2026-10-24T20:00:00Z"}),
        admin=MagicMock(return_value={"total_requests": 1, "est_cost_usd": "unknown"}),
    )
    monkeypatch.setattr(ask, "check_scope", lambda request: None)
    monkeypatch.setattr(cache, "scope_version", lambda subject: "v1")
    monkeypatch.setattr(cache, "get", mocks.cached)
    monkeypatch.setattr(cache, "put", mocks.put)
    monkeypatch.setattr(quota, "dubai_day", lambda: DAY)
    monkeypatch.setattr(quota, "try_consume", mocks.reserve)
    monkeypatch.setattr(quota, "record_usage", mocks.record)
    monkeypatch.setattr(quota, "remaining", mocks.remaining)
    monkeypatch.setattr(quota, "release_empty", mocks.release)
    monkeypatch.setattr(quota, "global_ok", mocks.global_ok)
    monkeypatch.setattr(quota, "user_usage", mocks.status)
    monkeypatch.setattr(quota, "admin_usage", mocks.admin)
    monkeypatch.setattr(ask, "answer_question", mocks.generate)
    main.app.dependency_overrides[get_current_user] = lambda: dict(USER)
    try:
        with TestClient(main.app) as client:
            yield client, mocks
    finally:
        main.app.dependency_overrides.clear()


def post(client, **kwargs):
    return client.post("/ask", json={"question": "paging", "subject_id": 1}, **kwargs)


def test_server_call_records_tokens_and_remaining(api):
    client, mocks = api
    response = post(client)
    assert response.status_code == 200
    assert response.json()["remaining"] == 4
    mocks.reserve.assert_called_once_with(USER["id"], DAY)
    mocks.record.assert_called_once_with(USER["id"], input_tokens=20, output_tokens=5, day=DAY)


def test_five_questions_then_block(api):
    client, mocks = api
    mocks.reserve.side_effect = [True] * 5 + [False]
    assert [post(client).status_code for _ in range(6)] == [200] * 5 + [429]
    assert mocks.generate.call_count == mocks.record.call_count == 5


def test_cache_hit_consumes_nothing(api):
    client, mocks = api
    mocks.cached.return_value = {**RESULT, "usage": {"input_tokens": 0, "output_tokens": 0}}
    assert post(client).json()["usage"]["input_tokens"] == 0
    mocks.reserve.assert_not_called()
    mocks.generate.assert_not_called()
    mocks.record.assert_not_called()


def test_byok_bypasses_all_server_limits_and_accounting(api):
    client, mocks = api
    mocks.reserve.return_value = mocks.global_ok.return_value = False
    assert post(client, headers={"X-User-Api-Key": "fake-user-key"}).status_code == 200
    mocks.reserve.assert_not_called()
    mocks.global_ok.assert_not_called()
    mocks.record.assert_not_called()
    assert mocks.generate.call_args.kwargs["api_key"].get_secret_value() == "fake-user-key"
    assert "fake-user-key" not in repr(mocks.put.call_args)


def test_global_cap_blocks_only_server_key(api):
    client, mocks = api
    mocks.reserve.return_value = mocks.global_ok.return_value = False
    assert post(client).status_code == 429
    mocks.generate.assert_not_called()
    assert post(client, headers={"X-User-Api-Key": "fake-key"}).status_code == 200


def test_empty_retrieval_returns_reservation(api):
    client, mocks = api
    mocks.generate.return_value = {"answer": NOT_FOUND, "sources": [],
                                   "usage": {"input_tokens": 0, "output_tokens": 0}}
    assert client.post("/ask", json={"question": "paging", "subject_id": 1, "mode": "strict"}).status_code == 200
    mocks.release.assert_called_once_with(USER["id"], DAY)
    mocks.record.assert_not_called()


def test_provider_error_never_reaches_cache_or_usage(api):
    client, mocks = api
    mocks.generate.side_effect = HTTPException(503, "Gemini is busy.")
    assert post(client).status_code == 503
    mocks.put.assert_not_called()
    mocks.record.assert_not_called()


def test_usage_and_admin_authorization(api):
    client, mocks = api
    assert client.get("/me/usage").json()["used"] == 1
    assert client.get("/admin/usage/today").status_code == 403
    mocks.admin.assert_not_called()
    main.app.dependency_overrides[get_current_user] = lambda: {**USER, "role": "admin"}
    assert client.get("/admin/usage/today").status_code == 200


@pytest.mark.parametrize("path,method", [
    ("/me/usage", "GET"), ("/admin/usage/today", "GET"), ("/me/test-key", "POST"),
])
def test_new_routes_require_authentication(api, path, method):
    client, _ = api
    main.app.dependency_overrides.clear()
    assert client.request(method, path).status_code == 401


def test_tiny_key_check_requires_and_uses_user_key(api, monkeypatch):
    client, mocks = api
    assert client.post("/me/test-key").status_code == 400
    model = MagicMock()
    constructor = MagicMock(return_value=model)
    monkeypatch.setattr(llm, "get_chat_model", constructor)
    assert client.post("/me/test-key", headers={"X-User-Api-Key": "fake-key"}).json() == {"ok": True}
    assert constructor.call_args.args[0].get_secret_value() == "fake-key"
    model.bind.assert_called_once_with(max_output_tokens=8)
    mocks.reserve.assert_not_called()
    mocks.record.assert_not_called()


def test_blank_key_is_rejected_without_echo(api):
    client, mocks = api
    assert post(client, headers={"X-User-Api-Key": " "}).status_code == 400
    mocks.generate.assert_not_called()


def test_provider_failure_is_safe_503():
    with pytest.raises(HTTPException) as error:
        with llm.provider_errors():
            raise RuntimeError("fake-private-key")
    assert error.value.status_code == 503
    assert "fake-private-key" not in error.value.detail


@pytest.mark.parametrize("header", ["Authorization", "X-User-Api-Key", "authorization"])
def test_header_logging_is_redacted(caplog, header):
    with caplog.at_level(logging.WARNING):
        logging.getLogger("phase5-test").warning("headers: %s", {header: "fake-private-key"})
    assert "fake-private-key" not in caplog.text
    assert "[redacted sensitive headers]" in caplog.text


def test_exception_header_logging_is_redacted(caplog):
    try:
        raise RuntimeError("X-User-Api-Key: fake-private-key")
    except RuntimeError:
        logging.getLogger("phase5-test").exception("Request failed")
    assert "fake-private-key" not in caplog.text


def test_key_check_failure_hides_provider_error(api, monkeypatch, caplog):
    client, mocks = api
    monkeypatch.setattr(llm, "get_chat_model", MagicMock(side_effect=RuntimeError("fake-private-key")))
    response = client.post("/me/test-key", headers={"X-User-Api-Key": "fake-private-key"})
    assert response.status_code == 503
    assert "fake-private-key" not in response.text + caplog.text
    mocks.record.assert_not_called()


def test_zero_context_capacity_skips_model(monkeypatch):
    hit = {"subject": "OS", "module": 2, "document": "Memory",
           "page": 1, "content": "notes", "score": 0.9}
    monkeypatch.setattr(answer, "Settings", lambda: SimpleNamespace(max_context_tokens=1))
    monkeypatch.setattr(answer, "retrieve", lambda *args: [hit])
    constructor = MagicMock()
    monkeypatch.setattr(answer, "get_chat_model", constructor)
    assert answer.answer_question("paging", 1, mode="strict")["sources"] == []
    constructor.assert_not_called()


def test_context_limit_preserves_only_supplied_sources():
    hits = [{"subject": "OS", "module": 2, "document": "Memory",
             "page": n, "content": "x" * 1000, "score": 0.9} for n in range(1, 4)]
    selected, context = answer.trim_context(hits, 50)
    assert len(context) <= 200
    assert len(selected) == 1
    assert "[1]" in context and "[2]" not in context


def test_context_limit_and_user_key_reach_model(monkeypatch):
    hit = {"subject": "OS", "module": 2, "document": "Memory",
           "page": 1, "content": "x" * 1000, "score": 0.9}
    monkeypatch.setattr(answer, "Settings", lambda: SimpleNamespace(max_context_tokens=50))
    monkeypatch.setattr(answer, "retrieve", lambda *args: [hit])
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="Answer [1]", usage_metadata={})
    constructor = MagicMock(return_value=model)
    monkeypatch.setattr(answer, "get_chat_model", constructor)
    key = SecretStr("fake-user-key")
    result = answer.answer_question("paging", 1, api_key=key)
    constructor.assert_called_once_with(key)
    context = model.invoke.call_args.args[0][1][1].split("Notes context:\n")[1].split("\n\nQuestion:")[0]
    assert len(context) <= 200
    assert len(result["sources"]) == 1

