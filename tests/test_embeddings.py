"""Verify embedding configuration without importing or downloading model weights.
Replace the LangChain constructor and settings before embedding is requested.
Test both retrieval prompts and reject vectors incompatible with the schema.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
import logging
import sys
from pathlib import Path

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
    constructor.return_value._client.__getitem__.return_value = SimpleNamespace(
        modality_config={"text": {"method": "forward"}, "message": {"format": "structured"},
                         "video": {}, "image": {}, "audio": {}},
        input_formatter=SimpleNamespace(supported_modalities=["text", "video", "image", "audio"]),
    )
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
    transformer = first._client[0]
    assert transformer.input_formatter.supported_modalities == ["text"]
    assert set(transformer.modality_config) == {"text", "message"}


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


@pytest.mark.parametrize("value", [{"text": "notes"}, {"role": "user", "content": "notes"}, Path("demo.mp4"), b"notes", 7, None])
def test_non_string_embedding_inputs_are_rejected_before_model_load(model_setup, value):
    _, constructor = model_setup
    with pytest.raises(TypeError, match="plain str"):
        embeddings.embed_documents(["valid", value])
    with pytest.raises(TypeError, match="plain str"):
        embeddings.embed_query(value)
    constructor.assert_not_called()


@pytest.mark.parametrize("value", ["not a list", {"text": "notes"}, ("notes",)])
def test_document_container_must_be_a_list(model_setup, value):
    _, constructor = model_setup
    with pytest.raises(TypeError, match="list of plain str"):
        embeddings.embed_documents(value)
    constructor.assert_not_called()


@pytest.mark.parametrize("text", [
    "demo.mp4", "demo.MOV", "lecture.avi", "https://example.invalid/demo.mp4?token=fake",
    "https://www.youtube.com/watch?v=example", "https://youtu.be/example",
    "file:///tmp/demo.mp4", r"C:\videos\demo.mp4",
])
def test_media_references_are_plain_text_for_document_and_query_encoding(model_setup, text):
    _, constructor = model_setup
    model = constructor.return_value
    model.embed_documents.return_value = [[0.0] * 768]
    model.embed_query.return_value = [0.0] * 768
    embeddings.embed_documents([text])
    embeddings.embed_query(text)
    document_text = model.embed_documents.call_args.args[0][0]
    query_text = model.embed_query.call_args.args[0]
    assert type(document_text) is str and type(query_text) is str
    assert document_text == query_text == "[media reference]"


def test_empty_chunks_are_skipped_and_normal_pdf_text_is_unchanged(model_setup):
    _, constructor = model_setup
    model = constructor.return_value
    model.embed_documents.return_value = [[0.0] * 768]
    text = "Virtual memory maps pages to physical frames."
    assert len(embeddings.embed_documents(["", "  \n ", text])) == 1
    model.embed_documents.assert_called_once_with([text])


def test_all_empty_chunks_do_not_load_model(model_setup):
    _, constructor = model_setup
    assert embeddings.embed_documents(["", " \n "]) == []
    with pytest.raises(ValueError, match="must not be empty"):
        embeddings.embed_query("  ")
    constructor.assert_not_called()


def test_real_huggingface_wrapper_and_formatter_never_route_text_to_video(model_setup):
    from langchain_huggingface import HuggingFaceEmbeddings
    from sentence_transformers.base.modality import InputFormatter
    _, constructor = model_setup
    formatter = InputFormatter(model_type="embedding_gemma2", supported_modalities=["text", "video", "message"])
    transformer = SimpleNamespace(modality_config={"text": {}, "video": {}, "message": {}}, input_formatter=formatter)
    client = MagicMock()
    client.__getitem__.return_value = transformer
    wrapper = HuggingFaceEmbeddings.model_construct(
        encode_kwargs={"prompt_name": "Document", "normalize_embeddings": True},
        query_encode_kwargs={"prompt_name": "SearchQuery", "normalize_embeddings": True},
    )
    wrapper._client = client
    constructor.return_value = wrapper

    def encode(texts, **kwargs):
        assert all(type(text) is str for text in texts)
        modality, values, _ = formatter.parse_inputs(texts)
        assert modality == "text"
        assert list(values) == ["text"]
        assert kwargs["prompt_name"] in {"Document", "SearchQuery"}
        return SimpleNamespace(tolist=lambda: [[0.0] * 768 for _ in texts])
    client.encode.side_effect = encode
    embeddings.embed_documents(["demo.mp4", "https://youtu.be/example"])
    embeddings.embed_query("https://example.invalid/demo.mp4")
    # Even a missed media pattern is classified as text at the actual formatter boundary.
    assert formatter.parse_inputs(["https://example.invalid/unmatched.mp4"])[0] == "text"


def test_failed_batch_identifies_the_individual_chunk_and_video_reason(model_setup):
    _, constructor = model_setup
    def fetch_videos():
        raise ImportError("fake-private-diagnostic https://private.invalid?token=fake")
    def encode(texts):
        if "bad text" in texts:
            fetch_videos()
        return [[0.0] * 768 for _ in texts]
    constructor.return_value.embed_documents.side_effect = encode
    with pytest.raises(embeddings.EmbeddingError, match="video preprocessing.*ImportError") as error:
        embeddings.embed_documents(["good text", "bad text"])
    assert error.value.chunk_index == 1
    assert "fake-private" not in str(error.value)
