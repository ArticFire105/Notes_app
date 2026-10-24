"""
Test Phase 4 authentication without external services.
Supabase is replaced by a deterministic fake.
Database calls use an in-memory mock.
No dotenv file is opened by these tests.

Domain checks cover the college address.
Uppercase addresses remain valid.
Other domains are rejected.
Lookalike suffixes are rejected too.

Bearer verification failures return 401.
Missing credentials return 401.
Disallowed college domains return 403.
Missing application profiles return 401.

Students cannot upload official documents.
Representatives cannot upload official documents.
Administrators pass the role dependency.
Uploader identity comes from the backend.

The identity cache avoids repeated remote verification.
Expired cache entries are verified again.
Expired tokens never authenticate from the cache.
Current roles are always loaded from the database.

The public health route stays available.
Application endpoints require bearer credentials.
The me endpoint returns only email and role.
Provider failures never expose exception text.

OTP tests use a fake email and code.
The helper keeps its session only in memory.
The helper never prints its fake access token.
These tests do not apply the SQL migration.
Live email delivery is verified manually in Supabase.
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app import auth, main
from scripts import get_token


def fake_token(exp=1000):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return "fake." + payload + ".signature"


@pytest.fixture
def backend(monkeypatch):
    auth._identity_cache.clear()
    settings = SimpleNamespace(supabase_url="https://example.invalid",
                               supabase_anon_key=SecretStr("fake-anon"),
                               allowed_email_domain="dxb.manipal.edu")
    monkeypatch.setattr(auth, "Settings", lambda: settings)
    clock = MagicMock(return_value=100)
    monkeypatch.setattr(auth, "time", clock)
    provider = MagicMock()
    provider.return_value.auth.get_user.return_value.user = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001", email="student@dxb.manipal.edu",
    )
    monkeypatch.setattr(auth, "create_client", provider)
    database = MagicMock()
    cursor = database.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"id": "00000000-0000-0000-0000-000000000001", "role": "student"}
    monkeypatch.setattr(auth, "get_conn", database)
    monkeypatch.setattr(main, "get_embedder", lambda: None)
    yield SimpleNamespace(provider=provider, cursor=cursor, clock=clock, settings=settings)
    auth._identity_cache.clear()


@pytest.mark.parametrize("email,allowed", [
    ("student@dxb.manipal.edu", True), ("STUDENT@DXB.MANIPAL.EDU", True),
    ("student@gmail.com", False), ("user@dxb.manipal.edu.evil.com", False),
    ("@dxb.manipal.edu", False), ("a@b@dxb.manipal.edu", False),
])
def test_college_domain(email, allowed):
    assert auth.is_allowed_email(email, "dxb.manipal.edu") is allowed


@pytest.mark.parametrize("method,path", [
    ("GET", "/subjects"), ("GET", "/subjects/1/modules"),
    ("GET", "/modules/1/documents"), ("GET", "/documents/00000000-0000-0000-0000-000000000001"),
    ("GET", "/documents/00000000-0000-0000-0000-000000000001/pdf-url"),
    ("POST", "/documents"), ("POST", "/ask"), ("GET", "/me"),
])
def test_routes_require_authentication(backend, method, path):
    with TestClient(main.app) as client:
        response = client.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    backend.provider.assert_not_called()
    backend.cursor.execute.assert_not_called()


def test_identity_cache_and_current_role(backend):
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer " + fake_token()}
        assert client.get("/health").status_code == 200
        assert client.get("/me", headers=headers).json() == {
            "email": "student@dxb.manipal.edu", "role": "student",
        }
        backend.cursor.fetchone.return_value["role"] = "admin"
        assert client.get("/me", headers=headers).json()["role"] == "admin"
        backend.provider.return_value.auth.get_user.assert_called_once()
        backend.clock.return_value = 161
        assert client.get("/me", headers=headers).status_code == 200
        assert backend.provider.return_value.auth.get_user.call_count == 2


@pytest.mark.parametrize("case,status", [
    ("invalid", 401), ("expired", 401), ("domain", 403), ("profile", 401),
])
def test_failed_authentication(backend, case, status, caplog):
    if case == "invalid":
        backend.provider.return_value.auth.get_user.side_effect = RuntimeError("fake-secret")
    elif case == "domain":
        backend.provider.return_value.auth.get_user.return_value.user.email = "student@example.com"
    elif case == "profile":
        backend.cursor.fetchone.return_value = None
    token = fake_token(99 if case == "expired" else 1000)
    with TestClient(main.app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == status
    assert "fake-secret" not in response.text + caplog.text


def test_cache_does_not_extend_token_lifetime(backend):
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer " + fake_token(110)}
        assert client.get("/me", headers=headers).status_code == 200
        backend.clock.return_value = 111
        assert client.get("/me", headers=headers).status_code == 401


@pytest.mark.parametrize("role", ["student", "rep"])
def test_upload_rejects_non_admin_before_work(backend, role):
    backend.cursor.fetchone.return_value["role"] = role
    with TestClient(main.app) as client:
        response = client.post("/documents", headers={"Authorization": "Bearer " + fake_token()})
    assert response.status_code == 403


@pytest.mark.parametrize("print_token", [False, True])
def test_otp_helper_token_output_is_opt_in(backend, monkeypatch, capsys, print_token):
    monkeypatch.setattr(get_token, "Settings", lambda: backend.settings)
    monkeypatch.setattr("builtins.input", lambda _: "student@dxb.manipal.edu")
    monkeypatch.setattr(get_token, "getpass", lambda _: "123456")
    provider = MagicMock()
    provider.return_value.auth.verify_otp.return_value.session.access_token = "fake-private-token"
    monkeypatch.setattr(get_token, "create_client", provider)
    response = MagicMock()
    response.return_value.__enter__.return_value.read.return_value = b'{"email":"student@dxb.manipal.edu","role":"student"}'
    monkeypatch.setattr(get_token, "urlopen", response)
    assert get_token.main(["--print-token"] if print_token else []) == 0
    output = capsys.readouterr().out
    if print_token:
        assert output == "fake-private-token\n"
        response.assert_not_called()
    else:
        assert "fake-private-token" not in output
        response.assert_called_once()
    provider.return_value.auth.verify_otp.assert_called_once_with({
        "email": "student@dxb.manipal.edu", "token": "123456", "type": "email",
    })


def test_otp_helper_failed_login_does_not_print_token(backend, monkeypatch, capsys):
    monkeypatch.setattr(get_token, "Settings", lambda: backend.settings)
    monkeypatch.setattr("builtins.input", lambda _: "student@dxb.manipal.edu")
    monkeypatch.setattr(get_token, "getpass", lambda _: "123456")
    provider = MagicMock()
    provider.return_value.auth.verify_otp.side_effect = RuntimeError("fake-private-token")
    monkeypatch.setattr(get_token, "create_client", provider)
    assert get_token.main(["--print-token"]) == 1
    output = capsys.readouterr().out
    assert "Login check failed" in output
    assert "fake-private-token" not in output
