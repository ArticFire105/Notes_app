"""Verify Phase 0 setup behavior before any live infrastructure check.

These tests run with pytest from the repository root.
They exercise configuration and the manual setup checker's decisions.
They do not attempt to prove that remote infrastructure is available.

All settings values are deliberately fake test data.
Dotenv loading is disabled for every settings instance in this file.
Relevant environment overrides are removed for repeatable defaults.
No real .env file is opened by the test suite.
Secret representations are checked before any external work.
Both ordinary repr and JSON output must redact credential values.
Validation errors must not include sensitive input text.
These checks protect the public debugging surface of configuration.

The database driver is replaced with an in-memory test double.
Its query results simulate installed or missing pgvector support.
Subject fixtures cover missing, extra, and incorrect codes.
Only the exact planned five-subject set should pass.
Recorded SQL calls must remain read-only select statements.

Connection errors deliberately contain a fake password.
The checker must report failure without echoing that password.
No test creates a real database connection.
The embedding library is replaced before it can load a model.

Fake vectors cover the required and an incorrect dimension.
A failing loader prints a fake token before raising an exception.
Neither its output nor its exception may expose that token.
No test downloads model weights or calls a hosted model.

The entry point is checked for success and partial failures.
Both independent checks must run even when one fails.
Live database and real embedding validation remain manual steps.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.config import Settings
from scripts import check_setup


@pytest.fixture
def settings(monkeypatch):
    values = {
        "database_url": "postgresql://dummy:dummy-password@invalid/database",
        "supabase_url": "https://example.invalid",
        "supabase_anon_key": "dummy-anon-key",
        "supabase_service_role_key": "dummy-service-key",
        "google_api_key": "dummy-google-key",
        "hf_token": "dummy-hf-token",
    }
    for name in (*values, "embedding_provider", "embedding_model", "embedding_dim", "chat_model"):
        monkeypatch.delenv(name.upper(), raising=False)
    # Explicitly disable dotenv so tests never touch a real .env.
    return Settings(_env_file=None, **values)


def test_settings_hide_credentials(settings):
    for field in (
        "database_url", "supabase_anon_key", "supabase_service_role_key",
        "google_api_key", "hf_token",
    ):
        assert getattr(settings, field).get_secret_value() not in repr(settings)
        assert getattr(settings, field).get_secret_value() not in settings.model_dump_json()


def test_embedding_dimension_from_environment(settings, monkeypatch):
    values = settings.model_dump()
    values.pop("embedding_dim")
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    configured = Settings(_env_file=None, **values)
    assert configured.embedding_dim == 768
    assert isinstance(configured.embedding_dim, int)


@pytest.mark.parametrize("dimension", [512, "512"])
def test_settings_reject_wrong_embedding_dimension(settings, dimension):
    values = settings.model_dump()
    values["embedding_dim"] = dimension
    with pytest.raises(ValidationError, match="embedding_dim must be 768"):
        Settings(_env_file=None, **values)


def test_wrong_dimension_does_not_echo_input(settings):
    values = settings.model_dump()
    values["embedding_dim"] = "dummy-sensitive-input"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "dummy-sensitive-input" not in str(error.value)


@pytest.mark.parametrize("codes,version,expected", [
    (["OS", "SE", "POC", "CN", "EOM"], ("0.8.0",), True),
    (["OS", "SE", "POC", "CN"], ("0.8.0",), False),
    (["OS", "SE", "POC", "CN", "EOM", "EXTRA"], ("0.8.0",), False),
    (["OS", "SE", "POC", "CN", "OTHER"], ("0.8.0",), False),
    (["OS", "SE", "POC", "CN", "EOM"], None, False),
])
def test_database_requirements(settings, monkeypatch, codes, version, expected):
    driver = MagicMock()
    cursor = driver.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = version
    cursor.fetchall.return_value = [(code, "Subject name") for code in codes]
    monkeypatch.setitem(sys.modules, "psycopg", driver)
    assert check_setup.check_database(settings) is expected
    for call in cursor.execute.call_args_list:
        assert call.args[0].startswith("select ")


def test_database_failure_hides_exception(settings, monkeypatch, capsys):
    driver = MagicMock()
    driver.connect.side_effect = RuntimeError(settings.database_url.get_secret_value())
    monkeypatch.setitem(sys.modules, "psycopg", driver)
    assert check_setup.check_database(settings) is False
    captured = capsys.readouterr()
    assert "FAIL database" in captured.out
    assert "dummy-password" not in captured.out + captured.err


@pytest.mark.parametrize("dimension,expected", [(768, True), (512, False)])
def test_embedding_dimension(settings, monkeypatch, dimension, expected):
    model = MagicMock()
    model.return_value.encode.return_value = [0.0] * dimension
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=model))
    assert check_setup.check_embedding(settings) is expected
    model.assert_called_once_with(settings.embedding_model, token="dummy-hf-token")


def test_embedding_failure_hides_library_output(settings, monkeypatch, capsys):
    def failing_model(*args, **kwargs):
        print("dummy-hf-token", file=sys.stderr)
        raise RuntimeError("dummy-hf-token")

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=failing_model))
    assert check_setup.check_embedding(settings) is False
    captured = capsys.readouterr()
    assert "FAIL embeddings" in captured.out
    assert "dummy-hf-token" not in captured.out + captured.err


def test_settings_failure_hides_exception(monkeypatch, capsys):
    def failing_settings():
        raise ValueError("dummy-secret")

    monkeypatch.setattr(check_setup, "Settings", failing_settings)
    assert check_setup.main() == 1
    captured = capsys.readouterr()
    assert "FAIL settings" in captured.out
    assert "dummy-secret" not in captured.out + captured.err


@pytest.mark.parametrize("database_ok,embedding_ok,exit_code", [
    (True, True, 0), (False, True, 1), (True, False, 1), (False, False, 1),
])
def test_main_reports_failure_and_runs_both_checks(
    settings, monkeypatch, database_ok, embedding_ok, exit_code
):
    monkeypatch.setattr(check_setup, "Settings", lambda: settings)
    database = MagicMock(return_value=database_ok)
    embedding = MagicMock(return_value=embedding_ok)
    monkeypatch.setattr(check_setup, "check_database", database)
    monkeypatch.setattr(check_setup, "check_embedding", embedding)
    assert check_setup.main() == exit_code
    database.assert_called_once_with(settings)
    embedding.assert_called_once_with(settings)
