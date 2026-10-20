"""
Verify scoped retrieval and evaluation with fake database results.
Settings are replaced before retrieval can load dotenv.
Query values must stay in the parameter list.
Version checks and module-number resolution use mocked cursors.

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

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.rag import retrieve as retrieval
from scripts import eval_retrieval


@pytest.fixture
def database(monkeypatch):
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"extversion": "0.8.0"}
    cursor.fetchall.return_value = [
        {"score": 0.4, "document": "Memory.pdf", "page": 14},
        {"score": 0.9, "document": "Memory.pdf", "page": 15},
    ]
    monkeypatch.setattr(retrieval, "get_conn", context)
    monkeypatch.setattr(retrieval, "Settings", lambda: SimpleNamespace(embedding_model="test-model"))
    embed = MagicMock(return_value=[0.0] * 768)
    monkeypatch.setattr(retrieval, "embed_query", embed)
    return cursor, embed


@pytest.mark.parametrize("version,iterative", [
    ("0.7.4", False), ("0.8.0", True), ("0.10.0", True), ("1.0.0", True),
])
def test_version_aware_iterative_scan_and_parameterized_filters(database, version, iterative):
    cursor, embed = database
    cursor.fetchone.return_value = {"extversion": version}
    document_id = UUID("00000000-0000-0000-0000-000000000001")
    hits = retrieval.retrieve("What is paging?", 1, 12, document_id, k=3)
    embed.assert_called_once_with("What is paging?")
    calls = cursor.execute.call_args_list
    assert any("SET LOCAL" in call.args[0] for call in calls) is iterative
    sql, params = calls[-1].args
    assert "c.source_type = 'official'" in sql
    assert "c.embedding_model = %s" in sql
    assert "c.module_id = %s" in sql and "c.document_id = %s" in sql
    assert "left join modules" in sql
    assert "order by c.embedding <=> %s" in sql
    assert params[1:5] == [1, "test-model", 12, document_id]
    assert params[-1] == 3
    assert params[0].dimensions() == 768
    assert [hit["score"] for hit in hits] == [0.9, 0.4]


def test_whole_subject_omits_optional_filters(database):
    cursor, _ = database
    retrieval.retrieve("paging", 1)
    sql, params = cursor.execute.call_args.args
    assert "c.module_id = %s" not in sql
    assert "c.document_id = %s" not in sql
    assert len(params) == 5


@pytest.mark.parametrize("question,k", [(" ", 5), ("paging", 0)])
def test_invalid_search_does_not_embed(database, question, k):
    _, embed = database
    with pytest.raises(ValueError):
        retrieval.retrieve(question, 1, k=k)
    embed.assert_not_called()


def test_resolves_module_number_within_subject(database):
    cursor, _ = database
    cursor.fetchone.side_effect = [(1,), (12,)]
    assert retrieval.resolve_scope(" os ", 2) == (1, 12)
    assert cursor.execute.call_args_list[0].args[1] == ("OS",)
    assert cursor.execute.call_args_list[1].args[1] == (1, 2)


def test_resolves_whole_subject_and_rejects_missing_scope(database):
    cursor, _ = database
    cursor.fetchone.side_effect = [(1,), None, (1,), None]
    assert retrieval.resolve_scope("OS") == (1, None)
    with pytest.raises(ValueError, match="Subject not found"):
        retrieval.resolve_scope("UNKNOWN")
    with pytest.raises(ValueError, match="Module not found"):
        retrieval.resolve_scope("OS", 99)


def test_evaluation_matches_both_document_and_page(monkeypatch):
    monkeypatch.setattr(eval_retrieval, "resolve_scope", MagicMock(return_value=(1, 12)))
    search = MagicMock(return_value=[
        {"document": "Other.pdf", "page": 14},
        {"document": "Memory.pdf", "page": 13},
        {"document": "Memory.pdf", "page": 14},
    ])
    monkeypatch.setattr(eval_retrieval, "retrieve", search)
    item = {"question": "paging", "subject": "OS", "module": 2,
            "expected_document": "Memory.pdf", "expected_page": 14}
    result = eval_retrieval.evaluate([item])
    assert result["counts"] == {1: 0, 3: 1, 5: 1}
    assert result["misses"] == {1: [item], 3: [], 5: []}
    search.assert_called_once_with("paging", 1, 12, k=5)


def test_evaluation_rejects_empty_input():
    with pytest.raises(ValueError):
        eval_retrieval.evaluate([])

