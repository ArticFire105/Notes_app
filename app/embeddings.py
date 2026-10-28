"""Share an embedder between ingestion and search.
Use Gemini document and query instructions for compatible vectors.
Reject incompatible dimensions before they reach vector(768) columns.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from functools import cache
import logging
import os
import re
import time
import random
from threading import Lock

import httpx

from app.config import Settings


MEDIA_REFERENCE = re.compile(
    r"file://[^\s<>\"']*|"
    r"(?:https?://|www\.)?(?:[\w-]+\.)?(?:youtube\.com|youtu\.be)(?:/[^\s<>\"']*)?|"
    r"[^\s<>\"']+\.(?:mp4|mov|avi|wmv|flv|mkv|webm|mp3|wav|ogg|flac|aac|jpg|jpeg|png|gif|webp)\b(?:[?#][^\s<>\"']*)?",
    re.IGNORECASE,
)


def HuggingFaceEmbeddings(**kwargs):
    # Loading the local libraries at import would slow down Gemini-only servers.
    from langchain_huggingface import HuggingFaceEmbeddings as LocalEmbeddings
    return LocalEmbeddings(**kwargs)


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


_request_lock = Lock()
_last_request = 0.0


class GeminiEmbedder:
    def __init__(self, settings):
        self.settings = settings
        if settings.embedding_model != "gemini-embedding-2":
            raise ValueError("Gemini embeddings require the gemini-embedding-2 model.")

    def _embed(self, texts):
        global _last_request
        model = "models/gemini-embedding-2"
        request = {"requests": [{"model": model, "content": {"parts": [{"text": text}]},
                                  "outputDimensionality": self.settings.embedding_dim} for text in texts]}
        for attempt in range(5):
            try:
                # Coordinate requests in this process, including concurrent uploads and searches.
                with _request_lock:
                    time.sleep(max(0, 1.0 - (time.monotonic() - _last_request)))
                    response = httpx.post("https://generativelanguage.googleapis.com/v1beta/" + model + ":batchEmbedContents",
                                          headers={"x-goog-api-key": self.settings.google_api_key.get_secret_value()},
                                          json=request, timeout=60.0)
                    _last_request = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 4:
                        time.sleep(min(30, 2 ** attempt + random.random()))
                        continue
                    raise EmbeddingError("Gemini embedding rate limit or service error. Try again later.")
                if response.status_code >= 400:
                    raise EmbeddingError(f"Gemini embedding request failed (HTTP {response.status_code}).")
                result = response.json()
                return [item["values"] for item in result["embeddings"]]
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 4:
                    raise EmbeddingError("Gemini embedding connection failed. Try again later.") from None
                time.sleep(min(30, 2 ** attempt + random.random()))
            except (KeyError, TypeError, ValueError):
                raise EmbeddingError("Gemini returned an invalid embedding response.") from None
        raise EmbeddingError("Gemini embedding request failed.")

    def embed_documents(self, texts):
        return self._embed(["title: none | text: " + text for text in texts])

    def embed_query(self, text):
        return self._embed(["task: search result | query: " + text])[0]


@cache
def get_embedder():
    settings = Settings()
    if settings.embedding_provider == "gemini":
        return GeminiEmbedder(settings)

    with _quiet_model_output():
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # Keep CPU work from oversubscribing small hosts.
        if device == "cpu":
            torch.set_num_threads(min(4, os.cpu_count() or 1))
        embedder = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={
                "device": device,
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
    logging.getLogger(__name__).info("Embedding device: %s", device)
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
    except EmbeddingError:
        raise
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
