"""
Verify answer generation without a real model or configuration.
Empty retrieval must skip chat construction completely.
Fake responses exercise citation metadata and token accounting.
CLI failures and noisy provider diagnostics must hide fake secrets.

This file belongs only to Phase 2 of the notes application.
The phase runs through scripts before an API is introduced.
Students can scope retrieval to a subject or a module.
Document IDs can further narrow the retrieval function.
Only official notes are eligible for these searches.
Embedding model identity keeps vector comparisons compatible.
The Phase 1 embedder remains responsible for query vectors.
The Phase 1 connection helper remains responsible for transactions.
Database values are passed separately from SQL text.
Module numbers are display labels rather than database IDs.
Original page numbers connect answers to the source notes.
Numbered context blocks give the model citation targets.
Source numbers follow the order supplied to the prompt.
An unsupported question must produce the not-found response.
Empty retrieval must not trigger a paid chat request.
Chat output is limited through the existing settings class.
Usage counts are returned for later accounting work.
No quota or cache behavior is introduced in this phase.
No authentication or frontend behavior is introduced here.
Real credentials belong only in the user's local configuration.
Secrets must never appear in printed exception diagnostics.
Offline tests replace settings and external service calls.
Tests must disable dotenv loading or replace Settings entirely.
Tests do not download weights or open live database connections.
Live source-page verification remains a manual check.
The evaluation example demonstrates the input format only.
Real evaluation questions stay outside version control.
Run the scripts from the repository root with uv.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from pydantic import SecretStr
import pytest

from app import llm
from app.config import Settings
from app.rag import answer
from app.rag.prompt import NOT_FOUND
from scripts import ask, eval_retrieval


@pytest.fixture(autouse=True)
def offline_context_settings(monkeypatch):
    monkeypatch.setattr(answer, "Settings", lambda: SimpleNamespace(max_context_tokens=4000))


@pytest.fixture
def hit():
    return {"subject": "OS", "module": 2, "module_title": "Memory",
            "document": "Memory.pdf", "page": 14, "content": "Paging uses pages.",
            "score": 0.9}


def test_empty_retrieval_skips_paid_model(monkeypatch):
    monkeypatch.setattr(answer, "retrieve", MagicMock(return_value=[]))
    model = MagicMock()
    monkeypatch.setattr(answer, "get_chat_model", model)
    assert answer.answer_question("paging", 1, 12) == {
        "answer": NOT_FOUND, "sources": [],
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    model.assert_not_called()


@pytest.mark.parametrize("content", ["Pages [1]", [{"type": "text", "text": "Pages [1]"}]])
def test_answer_keeps_scope_citations_and_tokens(monkeypatch, hit, content):
    search = MagicMock(return_value=[hit])
    model = MagicMock()
    model.return_value.invoke.return_value = SimpleNamespace(
        content=content, usage_metadata={"input_tokens": 100, "output_tokens": 10},
    )
    monkeypatch.setattr(answer, "retrieve", search)
    monkeypatch.setattr(answer, "get_chat_model", model)
    result = answer.answer_question("paging", 1, 12, "document-id")
    search.assert_called_once_with("paging", 1, 12, "document-id")
    assert result["answer"] == "Pages [1]"
    assert result["sources"] == [
        {"n": 1, "document": "Memory.pdf", "module": 2, "page": 14, "page_label": "p.14", "score": 0.9}
    ]
    assert result["usage"] == {"input_tokens": 100, "output_tokens": 10}
    messages = model.return_value.invoke.call_args.args[0]
    assert "primary evidence" in messages[0][1]
    assert "[1] (OS · Module 2 · Memory.pdf · p.14)" in messages[1][1]


def test_not_found_response_and_missing_usage(monkeypatch, hit):
    monkeypatch.setattr(answer, "retrieve", lambda *args: [hit])
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content=NOT_FOUND, usage_metadata=None)
    monkeypatch.setattr(answer, "get_chat_model", lambda: model)
    result = answer.answer_question("RSA?", 1, 12)
    assert result["answer"] == NOT_FOUND
    assert result["usage"] == {"input_tokens": 0, "output_tokens": 0}


def test_powerpoint_answer_returns_slide_source_label(monkeypatch, hit):
    hit.update(file_type="pptx", page=7)
    monkeypatch.setattr(answer, "retrieve", lambda *args: [hit])
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="See the slide [1].", usage_metadata=None)
    monkeypatch.setattr(answer, "get_chat_model", lambda: model)
    result = answer.answer_question("Explain the notes", 1, 12)
    assert result["sources"][0]["page"] == 7
    assert result["sources"][0]["page_label"] == "Slide 7"
    assert "Slide 7" in model.invoke.call_args.args[0][1][1]


@pytest.mark.parametrize("override,expected", [(None, "dummy-server"), ("dummy-user", "dummy-user")])
def test_model_configuration_and_key_override(monkeypatch, override, expected):
    settings = SimpleNamespace(google_api_key=SecretStr("dummy-server"),
                               chat_model="google_genai:test-model", max_output_tokens=321)
    monkeypatch.setattr(llm, "Settings", lambda: settings)
    constructor = MagicMock()
    monkeypatch.setattr(llm, "init_chat_model", constructor)
    assert llm.get_chat_model(override) is constructor.return_value
    constructor.assert_called_once_with(
        settings.chat_model, api_key=expected, temperature=0.2, max_output_tokens=321,
    )


def test_provider_output_is_quiet_and_logging_restored(capsys):
    previous = logging.root.manager.disable
    with pytest.raises(RuntimeError):
        with llm.quiet_chat_output():
            print("dummy-secret")
            logging.error("dummy-secret")
            raise RuntimeError("dummy-secret")
    captured = capsys.readouterr()
    assert "dummy-secret" not in captured.out + captured.err
    assert logging.root.manager.disable == previous


def test_output_limit_default_and_environment_override(monkeypatch):
    values = {
        "database_url": "dummy-db", "supabase_url": "https://example.invalid",
        "supabase_anon_key": "dummy", "supabase_service_role_key": "dummy",
        "google_api_key": "dummy", "hf_token": "dummy",
    }
    monkeypatch.delenv("MAX_OUTPUT_TOKENS", raising=False)
    assert Settings(_env_file=None, **values).max_output_tokens == 800
    monkeypatch.setenv("MAX_OUTPUT_TOKENS", "400")
    assert Settings(_env_file=None, **values).max_output_tokens == 400


def test_phase_five_settings_without_dotenv(monkeypatch):
    values = {
        "database_url": "dummy-db", "supabase_url": "https://example.invalid",
        "supabase_anon_key": "dummy", "supabase_service_role_key": "dummy",
        "google_api_key": "dummy", "hf_token": "dummy",
    }
    monkeypatch.setenv("GLOBAL_DAILY_BUDGET_USD", "")
    assert Settings(_env_file=None, **values).global_daily_budget_usd is None
    monkeypatch.setenv("GLOBAL_DAILY_BUDGET_USD", "1.25")
    assert str(Settings(_env_file=None, **values).global_daily_budget_usd) == "1.25"
    monkeypatch.setenv("QUESTIONS_PER_DAY", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_ask_cli_prints_answer_sources_usage(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ask.py", "--subject", "OS", "--module", "2", "paging"])
    monkeypatch.setattr(ask, "resolve_scope", MagicMock(return_value=(1, 12)))
    generate = MagicMock(return_value={
        "answer": "Pages [1]",
        "sources": [{"n": 1, "document": "Memory.pdf", "module": 2, "page": 14, "score": 0.9}],
        "usage": {"input_tokens": 100, "output_tokens": 10},
    })
    monkeypatch.setattr(ask, "answer_question", generate)
    assert ask.main() == 0
    output = capsys.readouterr().out
    assert "Pages [1]" in output and "p.14" in output and "input=100" in output
    generate.assert_called_once_with("paging", 1, 12)


@pytest.mark.parametrize("cli,argv", [
    (ask, ["ask.py", "--subject", "OS", "paging"]),
    (eval_retrieval, ["eval_retrieval.py"]),
])
def test_cli_errors_hide_external_exceptions(monkeypatch, capsys, cli, argv):
    monkeypatch.setattr("sys.argv", argv)
    if cli is ask:
        monkeypatch.setattr(cli, "resolve_scope", MagicMock(side_effect=RuntimeError("dummy-secret")))
    else:
        monkeypatch.setattr(cli.Path, "read_text", MagicMock(side_effect=RuntimeError("dummy-secret")))
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
    assert "dummy-secret" not in captured.out + captured.err


def test_eval_cli_reads_file_and_reports_misses(monkeypatch, tmp_path, capsys):
    source = tmp_path / "questions.json"
    source.write_text('[{"question": "paging", "subject": "OS", "module": 2, '
                      '"expected_document": "Memory.pdf", "expected_page": 14}]', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["eval_retrieval.py", "--questions", str(source)])
    monkeypatch.setattr(eval_retrieval, "resolve_scope", lambda *args: (1, 12))
    monkeypatch.setattr(eval_retrieval, "retrieve", lambda *args, **kwargs: [])
    assert eval_retrieval.main() == 0
    output = capsys.readouterr().out
    assert "hit@1: 0/1" in output and "hit@3: 0/1" in output and "hit@5: 0/1" in output
    assert "MISS: paging" in output

