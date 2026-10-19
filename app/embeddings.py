"""Share one cached local embedder between ingestion and later query embedding.
Use the model card's separate document and query prompts with normalized vectors.
Reject incompatible dimensions before they reach the vector(768) database column.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from functools import cache
import logging
import os

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import Settings


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
        return HuggingFaceEmbeddings(
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


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with _quiet_model_output():
        vectors = get_embedder().embed_documents(texts)
    dimension = Settings().embedding_dim
    if len(vectors) != len(texts):
        raise ValueError("The embedder must return one vector per chunk.")
    if any(len(vector) != dimension for vector in vectors):
        raise ValueError("Document embeddings must have 768 dimensions.")
    return vectors


def embed_query(text: str) -> list[float]:
    with _quiet_model_output():
        vector = get_embedder().embed_query(text)
    if len(vector) != Settings().embedding_dim:
        raise ValueError("Query embeddings must have 768 dimensions.")
    return vector
