"""Share one cached local embedder between ingestion and later query embedding.
Use the model card's separate document and query prompts with normalized vectors.
Reject incompatible dimensions before they reach the vector(768) database column.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from functools import cache
import logging
import os
import re

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import Settings


MEDIA_REFERENCE = re.compile(
    r"file://[^\s<>\"']*|"
    r"(?:https?://|www\.)?(?:[\w-]+\.)?(?:youtube\.com|youtu\.be)(?:/[^\s<>\"']*)?|"
    r"[^\s<>\"']+\.(?:mp4|mov|avi|wmv|flv|mkv|webm|mp3|wav|ogg|flac|aac|jpg|jpeg|png|gif|webp)\b(?:[?#][^\s<>\"']*)?",
    re.IGNORECASE,
)


class EmbeddingError(RuntimeError):
    """A failed text embedding with a safe reason and optional batch position."""

    def __init__(self, reason, chunk_index=None):
        super().__init__(reason)
        self.safe_reason = reason
        self.chunk_index = chunk_index


def prepare_embedding_text(text: str) -> str:
    if type(text) is not str:
        raise TypeError("Embedding input must be a plain str, not a message, dictionary, or path object.")
    return MEDIA_REFERENCE.sub("[media reference]", text).strip()


def embedding_failure_reason(error: Exception) -> str:
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        trace = current.__traceback__
        while trace is not None:
            if trace.tb_frame.f_code.co_name in {"fetch_videos", "_process_videos"}:
                return f"Text embedding incorrectly entered video preprocessing ({type(current).__name__})."
            trace = trace.tb_next
        current = current.__cause__ or current.__context__
    return f"Text embedding failed ({type(error).__name__}). See the backend traceback."


@contextmanager
def _quiet_model_output():
    previous_level = logging.root.manager.disable
    try:
        # Download errors can contain authenticated URLs; the CLI reports a
        # fixed failure message rather than forwarding third-party diagnostics.
        with open(os.devnull, "w") as quiet:
            with redirect_stdout(quiet), redirect_stderr(quiet):
                logging.disable(logging.CRITICAL)
                yield
    finally:
        logging.disable(previous_level)


@cache
def get_embedder() -> HuggingFaceEmbeddings:
    settings = Settings()
    if settings.embedding_provider == "gemini":
        # Phase 10 fallback for low-RAM hosts.
        raise NotImplementedError("Gemini embeddings are deferred to Phase 10.")

    with _quiet_model_output():
        embedder = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={
                "device": "cpu",
                "token": settings.hf_token.get_secret_value(),
                "config_kwargs": {"vision_config": None, "audio_config": None},
            },
            # https://huggingface.co/google/embeddinggemma-2#quick-start
            encode_kwargs={"prompt_name": "Document", "normalize_embeddings": True},
            query_encode_kwargs={"prompt_name": "SearchQuery", "normalize_embeddings": True},
        )
        transformer = embedder._client[0]
        if "text" not in transformer.modality_config:
            raise ValueError("The embedding model must support text input.")
        # Disable media inference without changing the text/chat prompt formatting used by existing PDFs.
        transformer.modality_config = {
            name: config for name, config in transformer.modality_config.items()
            if name in {"text", "message"}
        }
        transformer.input_formatter.supported_modalities = ["text"]
        return embedder


def embed_documents(texts: list[str]) -> list[list[float]]:
    if type(texts) is not list:
        raise TypeError("Document embeddings require a list of plain str values.")
    texts = [prepare_embedding_text(text) for text in texts]
    texts = [text for text in texts if text]
    if not texts:
        return []
    with _quiet_model_output():
        embedder = get_embedder()
    try:
        with _quiet_model_output():
            vectors = embedder.embed_documents(texts)
    except Exception as error:
        # Diagnose only a failed batch; successful PDF ingestion keeps its normal batched path.
        for index, text in enumerate(texts):
            try:
                with _quiet_model_output():
                    embedder.embed_documents([text])
            except Exception as chunk_error:
                raise EmbeddingError(embedding_failure_reason(chunk_error), index) from chunk_error
        raise EmbeddingError(embedding_failure_reason(error)) from error
    dimension = Settings().embedding_dim
    if len(vectors) != len(texts):
        raise ValueError("The embedder must return one vector per chunk.")
    if any(len(vector) != dimension for vector in vectors):
        raise ValueError("Document embeddings must have 768 dimensions.")
    return vectors


def embed_query(text: str) -> list[float]:
    text = prepare_embedding_text(text)
    if not text:
        raise ValueError("Query text must not be empty.")
    try:
        with _quiet_model_output():
            vector = get_embedder().embed_query(text)
    except Exception as error:
        raise EmbeddingError(embedding_failure_reason(error)) from error
    if len(vector) != Settings().embedding_dim:
        raise ValueError("Query embeddings must have 768 dimensions.")
    return vector
