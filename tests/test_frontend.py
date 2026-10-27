"""
Verify session isolation and the backend-only Phase 6 HTTP boundary.
Mocked Streamlit screens and auth providers never use real credentials.
This file implements only Phase 6.
The UI communicates with FastAPI over HTTP.
Database access belongs to the backend.
Service role credentials belong to the backend.
Frontend configuration uses the process environment.
No frontend code loads a dotenv file.
Access tokens belong to Streamlit session state.
Refresh tokens belong to Streamlit session state.
User API keys belong to Streamlit session state.
Secrets never belong in URLs.
Secrets never belong in cached functions.
Secrets never belong in log messages.
Raw provider errors are hidden.
Backend authorization remains authoritative.
Roles come from the current user profile.
Official notes define the available question scope.
Module database IDs differ from display numbers.
PDF links are signed by the backend.
Chat histories are separated by subject.
Sources remain attached to their answers.
Daily allowance comes from the backend.
BYOK requests use a request header.
Uploads use the existing PDF endpoint.
Ingestion status is checked separately.
Later phase pages remain placeholders.
Functions stay small to support learning.
Tests replace remote services.
Tests do not open real dotenv files.
Live email delivery requires manual testing.
Run uv run pytest from the repository root.
Start FastAPI before starting Streamlit.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from streamlit.testing.v1 import AppTest
from streamlit.runtime.pages_manager import PagesManager

from app import main
from app.routers import login
from frontend import api_client as api
from frontend.pages import subject

ROOT = Path(__file__).resolve().parents[1]
FAKE_SUBJECT = {"id": 1, "code": "OS", "name": "Operating Systems"}
FAKE_MODULE = {"id": 12, "subject_id": 1, "number": 2, "title": "Memory"}
FAKE_DOCUMENT = {"id": "fake-document", "title": "Memory.pdf", "status": "ready"}
FAKE_USAGE = {"used": 1, "limit": 5, "resets_at": "2026-10-25T00:00:00+04:00"}
FAKE_ANSWER = {"answer": "Paging uses pages [1].", "remaining": 3,
               "sources": [{"n": 1, "module": 2, "document": "Memory.pdf",
                            "page": 14, "score": 0.82}]}


@pytest.fixture
def transport(monkeypatch):
    state = {"access_token": "fake-access", "refresh_token": "fake-refresh",
             "user_api_key": "fake-user-key"}
    monkeypatch.setattr(api.st, "session_state", state)
    calls = []
    responses = []
    def handler(request):
        calls.append(request)
        return responses.pop(0)
    client_type = httpx.Client
    monkeypatch.setattr(api.httpx, "Client",
                        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("API_BASE_URL", "http://backend.invalid")
    return state, calls, responses


def test_headers_and_scope_stay_at_backend(transport):
    state, calls, responses = transport
    responses.extend([httpx.Response(200, json=FAKE_ANSWER), httpx.Response(200, json=[])])
    api.ask("What is paging?", 1, 12, "fake-document")
    api.subjects()
    assert str(calls[0].url) == "http://backend.invalid/ask"
    assert calls[0].headers["authorization"] == "Bearer fake-access"
    assert calls[0].headers["x-user-api-key"] == "fake-user-key"
    assert "fake-user-key" not in str(calls[0].url)
    assert "x-user-api-key" not in calls[1].headers
    import json
    assert json.loads(calls[0].content) == {
        "question": "What is paging?", "subject_id": 1, "module_id": 12,
        "document_id": "fake-document",
    }


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 503])
def test_http_errors_hide_provider_content(transport, status):
    state, calls, responses = transport
    responses.append(httpx.Response(status, json={"detail": "fake-sensitive-provider-diagnostic"}))
    with pytest.raises(api.ApiError) as error:
        api.me()
    assert "fake-sensitive-provider-diagnostic" not in str(error.value)
    assert error.value.status == status
    if status == 401:
        assert state == {}


def test_refresh_rotates_session_before_authenticated_request(transport):
    state, calls, responses = transport
    state["expires_at"] = 1
    responses.extend([
        httpx.Response(200, json={"access_token": "fake-new", "refresh_token": "fake-rotated",
                                  "expires_at": 9999999999}),
        httpx.Response(200, json={"role": "student"}),
    ])
    api.me()
    assert calls[0].url.path == "/auth/refresh"
    assert "authorization" not in calls[0].headers
    assert calls[1].headers["authorization"] == "Bearer fake-new"
    assert state["refresh_token"] == "fake-rotated"


def test_failed_refresh_clears_all_private_state(transport):
    state, calls, responses = transport
    state.update(expires_at=1, histories={1: ["private history"]})
    responses.append(httpx.Response(401))
    with pytest.raises(api.ApiError):
        api.me()
    assert state == {}


def test_public_login_sends_no_stale_credentials(transport):
    state, calls, responses = transport
    responses.append(httpx.Response(200, json={"message": "sent"}))
    api.send_code("student@dxb.manipal.edu")
    assert "authorization" not in calls[0].headers
    assert "x-user-api-key" not in calls[0].headers


@pytest.mark.parametrize("scope,expected", [
    ("This module", (12, None)),
    ("This PDF", (12, "fake-document")),
    ("Whole subject", (None, None)),
])
def test_scope_uses_database_ids(scope, expected):
    assert subject.scope_ids(scope, FAKE_MODULE, FAKE_DOCUMENT) == expected


def test_pdf_scope_requires_document():
    with pytest.raises(ValueError):
        subject.scope_ids("This PDF", FAKE_MODULE, None)


@pytest.fixture
def auth_backend(monkeypatch):
    provider = MagicMock()
    session = SimpleNamespace(
        access_token="fake-access", refresh_token="fake-refresh", expires_at=9999999999,
        user=SimpleNamespace(email="student@dxb.manipal.edu"),
    )
    provider.auth.verify_otp.return_value.session = session
    provider.auth.refresh_session.return_value.session = session
    settings = SimpleNamespace(allowed_email_domain="dxb.manipal.edu")
    monkeypatch.setattr(login, "login_client", lambda: (settings, provider))
    monkeypatch.setattr(main, "get_embedder", lambda: None)
    with TestClient(main.create_app()) as client:
        yield client, provider


@pytest.mark.parametrize("email", ["student@gmail.com", "x@dxb.manipal.edu.evil", "@dxb.manipal.edu"])
def test_backend_rejects_noncollege_before_sending(auth_backend, email):
    client, provider = auth_backend
    assert client.post("/auth/send-code", json={"email": email}).status_code == 403
    provider.auth.sign_in_with_otp.assert_not_called()


def test_backend_otp_and_refresh_are_not_cacheable(auth_backend):
    client, provider = auth_backend
    assert client.post("/auth/send-code", json={"email": "STUDENT@DXB.MANIPAL.EDU"}).status_code == 200
    provider.auth.sign_in_with_otp.assert_called_once_with({"email": "student@dxb.manipal.edu"})
    for path, body in [
        ("/auth/verify", {"email": "student@dxb.manipal.edu", "code": "123456"}),
        ("/auth/refresh", {"refresh_token": "fake-refresh"}),
    ]:
        response = client.post(path, json=body)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["access_token"] == "fake-access"


@pytest.mark.parametrize("code", ["12345", "123456789", "abcdef", "１２３４５６"])
def test_backend_rejects_invalid_otp_lengths_or_characters(auth_backend, code):
    client, provider = auth_backend
    response = client.post("/auth/verify", json={"email": "student@dxb.manipal.edu", "code": code})
    assert response.status_code == 400
    provider.auth.verify_otp.assert_not_called()


@pytest.mark.parametrize("code", ["123456", "1234567", "12345678"])
def test_backend_accepts_six_to_eight_digit_codes(auth_backend, code):
    client, provider = auth_backend
    response = client.post("/auth/verify", json={"email": "student@dxb.manipal.edu", "code": code})
    assert response.status_code == 200
    provider.auth.verify_otp.assert_called_once_with(
        {"email": "student@dxb.manipal.edu", "token": code, "type": "email"}
    )


def test_browser_cors_allows_local_frontend(auth_backend):
    client, provider = auth_backend
    response = client.options("/ask", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,x-user-api-key",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_browser_cors_rejects_other_origins(auth_backend):
    client, provider = auth_backend
    response = client.options("/ask", headers={
        "Origin": "https://unrelated.invalid",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_otp_provider_errors_do_not_leak(auth_backend):
    client, provider = auth_backend
    provider.auth.verify_otp.side_effect = RuntimeError("fake-sensitive-auth-error")
    response = client.post("/auth/verify", json={"email": "student@dxb.manipal.edu", "code": "123456"})
    assert response.status_code == 401
    assert "fake-sensitive-auth-error" not in response.text


def test_anon_client_disables_persistence(monkeypatch):
    settings = SimpleNamespace(supabase_url="https://example.invalid",
                               supabase_anon_key=SecretStr("fake-anon"))
    monkeypatch.setattr(login, "Settings", lambda: settings)
    create = MagicMock()
    monkeypatch.setattr(login, "create_client", create)
    login.login_client()
    options = create.call_args.kwargs["options"]
    assert options.persist_session is False
    assert options.auto_refresh_token is False


@pytest.fixture
def screens(monkeypatch):
    # AppTest recreates PagesManager on each rerun and re-enables legacy pages/.
    # Keep the real app's st.navigation mode across simulated reruns.
    original_init = PagesManager.__init__
    def init_navigation(manager, *args, **kwargs):
        PagesManager.uses_pages_directory = False
        original_init(manager, *args, **kwargs)
    monkeypatch.setattr(PagesManager, "__init__", init_navigation)
    monkeypatch.setattr(api, "me", lambda: {"email": "student@dxb.manipal.edu", "role": "student"})
    monkeypatch.setattr(api, "subjects", lambda: [FAKE_SUBJECT])
    monkeypatch.setattr(api, "modules", lambda subject_id: [FAKE_MODULE])
    monkeypatch.setattr(api, "documents", lambda module_id: [FAKE_DOCUMENT])
    monkeypatch.setattr(api, "usage", lambda: FAKE_USAGE)
    return AppTest.from_file(str(ROOT / "frontend/app.py"))


def test_login_gate_and_domain_validation(screens):
    screens.run()
    assert not screens.exception
    screens.text_input[0].set_value("student@gmail.com")
    screens.button[0].click().run()
    assert "college email" in screens.error[0].value
    assert "access_token" not in screens.session_state


def test_home_card_opens_subject(screens):
    screens.session_state["access_token"] = "fake-access"
    screens.run()
    assert not screens.exception
    assert screens.subheader[0].value == "OS"
    screens.button(key="open_1").click().run()
    assert not screens.exception
    assert screens.title[0].value == "OS · Operating Systems"


def test_subject_chat_scope_sources_and_isolation(screens, monkeypatch):
    ask = MagicMock(return_value=FAKE_ANSWER)
    monkeypatch.setattr(api, "ask", ask)
    screens.session_state["access_token"] = "fake-access"
    screens.session_state["histories"] = {2: [{"role": "user", "content": "Other subject private chat"}]}
    screens.run()
    screens.button(key="open_1").click().run()
    screens.chat_input[0].set_value("What is paging?").run()
    assert not screens.exception
    ask.assert_called_once_with("What is paging?", 1, 12, None)
    assert len(screens.session_state["histories"][1]) == 2
    assert screens.session_state["histories"][2][0]["content"] == "Other subject private chat"
    assert any("p.14 (score 0.82)" in item.value for item in screens.text)
    screens.radio[0].set_value("Whole subject").run()
    screens.chat_input[0].set_value("What is paging across notes?").run()
    assert ask.call_args.args == ("What is paging across notes?", 1, None, None)


def test_logout_clears_credentials_and_histories(screens):
    screens.session_state["access_token"] = "fake-access"
    screens.session_state["user_api_key"] = "fake-user-key"
    screens.session_state["histories"] = {1: ["private history"]}
    screens.run()
    screens.sidebar.button[0].click().run()
    assert not screens.exception
    for name in ("access_token", "refresh_token", "user_api_key", "histories"):
        assert name not in screens.session_state


def test_frontend_does_not_import_backend_or_supabase():
    for path in (ROOT / "frontend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from app." not in source
        assert "import supabase" not in source
        assert "service_role" not in source
        assert "Settings(" not in source


def settings_screen():
    from frontend.pages.settings import render
    render()


def upload_screen():
    from frontend.pages.admin_upload import render
    render()


def test_settings_key_can_be_tested_and_removed(monkeypatch):
    monkeypatch.setattr(api, "usage", lambda: FAKE_USAGE)
    check = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(api, "test_key", check)
    screen = AppTest.from_function(settings_screen).run()
    screen.text_input[0].set_value("fake-user-key").run()
    assert screen.session_state["user_api_key"] == "fake-user-key"
    screen.button[1].click().run()
    check.assert_called_once()
    screen.button[0].click().run()
    assert not screen.exception
    assert "user_api_key" not in screen.session_state
    assert screen.text_input[0].value == ""


def test_settings_restores_key_after_widget_cleanup(monkeypatch):
    monkeypatch.setattr(api, "usage", lambda: FAKE_USAGE)
    screen = AppTest.from_function(settings_screen)
    screen.session_state["user_api_key"] = "fake-retained-key"
    screen.run()
    assert not screen.exception
    assert screen.text_input[0].value == "fake-retained-key"


def test_student_navigation_hides_admin_upload(screens):
    screens.session_state["access_token"] = "fake-access"
    screens.run()
    assert all(page["page_name"] != "Admin upload" for page in screens._registered_pages.values())


def test_admin_navigation_shows_upload(screens, monkeypatch):
    monkeypatch.setattr(api, "me", lambda: {"email": "admin@dxb.manipal.edu", "role": "admin"})
    screens.session_state["access_token"] = "fake-access"
    screens.run()
    assert not screens.exception
    assert any(page["page_name"] == "Admin upload" for page in screens._registered_pages.values())


@pytest.mark.parametrize("status,kind", [("processing", "info"), ("ready", "success"), ("failed", "error")])
def test_upload_polling_handles_terminal_states(monkeypatch, status, kind):
    from frontend.pages import admin_upload
    # Exercise each poll result without keeping AppTest's timer running forever.
    monkeypatch.setattr(admin_upload, "upload_status", admin_upload.upload_status.__wrapped__)
    monkeypatch.setattr(api, "me", lambda: {"role": "admin"})
    monkeypatch.setattr(api, "subjects", lambda: [FAKE_SUBJECT])
    monkeypatch.setattr(api, "modules", lambda subject_id: [FAKE_MODULE])
    monkeypatch.setattr(api, "document_status", lambda document_id: {**FAKE_DOCUMENT, "status": status})
    screen = AppTest.from_function(upload_screen)
    screen.session_state["pending_upload"] = "fake-document"
    screen.run()
    assert not screen.exception
    assert len(screen.get(kind)) == 1
    assert ("pending_upload" in screen.session_state) == (status == "processing")


def test_upload_screen_rechecks_role(monkeypatch):
    monkeypatch.setattr(api, "me", lambda: {"role": "student"})
    screen = AppTest.from_function(upload_screen).run()
    assert not screen.exception
    assert screen.error[0].value == "Administrator access required."
    assert len(screen.file_uploader) == 0


def test_refresh_rejects_noncollege_identity(auth_backend):
    client, provider = auth_backend
    provider.auth.refresh_session.return_value.session.user.email = "user@example.com"
    response = client.post("/auth/refresh", json={"refresh_token": "fake-refresh"})
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_browser_cookie_session_rotation_and_logout(auth_backend):
    client, provider = auth_backend
    headers = {"X-Browser-Session": "1"}
    verified = client.post("/auth/verify", headers=headers, json={"email": "student@dxb.manipal.edu", "code": "123456"})
    assert verified.status_code == 200
    assert "refresh_token" not in verified.json()
    assert "HttpOnly" in verified.headers["set-cookie"]
    assert "SameSite=lax" in verified.headers["set-cookie"]
    refreshed = client.post("/auth/refresh", headers=headers)
    assert refreshed.status_code == 200
    assert "refresh_token" not in refreshed.json()
    assert client.post("/auth/refresh").status_code == 403
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.post("/auth/refresh", headers=headers).status_code == 401
