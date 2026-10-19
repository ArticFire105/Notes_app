"""Verify embedding configuration without importing or downloading model weights.
Replace the LangChain constructor and settings before embedding is requested.
Test both retrieval prompts and reject vectors incompatible with the schema.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
import logging
import sys

from pydantic import SecretStr
import pytest

from app import embeddings


@pytest.fixture
def model_setup(monkeypatch):
    settings = SimpleNamespace(
        embedding_provider="local", embedding_model="google/embeddinggemma-2",
        embedding_dim=768, hf_token=SecretStr("dummy-token"),
    )
    constructor = MagicMock()
    monkeypatch.setattr(embeddings, "Settings", lambda: settings)
    monkeypatch.setattr(embeddings, "HuggingFaceEmbeddings", constructor)
    embeddings.get_embedder.cache_clear()
    yield settings, constructor
    embeddings.get_embedder.cache_clear()


def test_cached_model_uses_text_only_and_card_prompts(model_setup):
    settings, constructor = model_setup
    first = embeddings.get_embedder()
    assert embeddings.get_embedder() is first
    constructor.assert_called_once_with(
        model_name=settings.embedding_model,
        model_kwargs={
            "device": "cpu", "token": "dummy-token",
            "config_kwargs": {"vision_config": None, "audio_config": None},
        },
        encode_kwargs={"prompt_name": "Document", "normalize_embeddings": True},
        query_encode_kwargs={"prompt_name": "SearchQuery", "normalize_embeddings": True},
    )


def test_documents_and_query_use_their_respective_methods(model_setup):
    _, constructor = model_setup
    model = constructor.return_value
    model.embed_documents.return_value = [[0.0] * 768, [1.0] * 768]
    model.embed_query.return_value = [1.0] * 768
    assert len(embeddings.embed_documents(["first", "second"])) == 2
    assert len(embeddings.embed_query("question")) == 768
    model.embed_documents.assert_called_once_with(["first", "second"])
    model.embed_query.assert_called_once_with("question")


@pytest.mark.parametrize("vectors", [[[0.0] * 512], [], [[0.0] * 768] * 2])
def test_bad_document_vectors_are_rejected(model_setup, vectors):
    _, constructor = model_setup
    constructor.return_value.embed_documents.return_value = vectors
    with pytest.raises(ValueError):
        embeddings.embed_documents(["one chunk"])


def test_bad_query_vector_is_rejected(model_setup):
    _, constructor = model_setup
    constructor.return_value.embed_query.return_value = [0.0] * 512
    with pytest.raises(ValueError, match="768"):
        embeddings.embed_query("question")


def test_empty_input_does_not_load_model(model_setup):
    _, constructor = model_setup
    assert embeddings.embed_documents([]) == []
    constructor.assert_not_called()


def test_gemini_branch_is_explicitly_deferred(model_setup):
    settings, constructor = model_setup
    settings.embedding_provider = "gemini"
    with pytest.raises(NotImplementedError, match="Phase 10"):
        embeddings.get_embedder()
    constructor.assert_not_called()


def test_model_diagnostics_are_suppressed_and_logging_restored(model_setup, capsys):
    _, constructor = model_setup
    previous_level = logging.root.manager.disable

    def failing_constructor(**kwargs):
        print("dummy-token")
        print("dummy-token", file=sys.stderr)
        logging.error("dummy-token")
        raise RuntimeError("dummy-token")

    constructor.side_effect = failing_constructor
    with pytest.raises(RuntimeError):
        embeddings.get_embedder()
    captured = capsys.readouterr()
    assert "dummy-token" not in captured.out + captured.err
    assert logging.root.manager.disable == previous_level
