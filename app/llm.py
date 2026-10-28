"""
Create the Gemini chat model using existing settings.
The default key comes from the backend configuration.
An explicit request-only key override supports Phase 5 BYOK.
Quiet library calls prevent third-party diagnostics exposing credentials.

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
The router handles quotas and caches around answer generation.
Provider errors become fixed messages without secret diagnostics.
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

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import logging
import os

from langchain.chat_models import init_chat_model
from fastapi import HTTPException, Request
from pydantic import SecretStr

from app.config import Settings


@contextmanager
def quiet_chat_output():
    previous_level = logging.root.manager.disable
    try:
        # Provider failures can include authenticated URLs or request details.
        with open(os.devnull, "w") as quiet:
            with redirect_stdout(quiet), redirect_stderr(quiet):
                logging.disable(logging.CRITICAL)
                yield
    finally:
        logging.disable(previous_level)


def get_chat_model(api_key=None):
    settings = Settings()
    key = settings.google_api_key.get_secret_value() if api_key is None else api_key
    if isinstance(key, SecretStr):
        key = key.get_secret_value()
    with quiet_chat_output():
        return init_chat_model(
            settings.chat_model,
            api_key=key,
            temperature=0.2,
            max_output_tokens=settings.max_output_tokens,
        )


def user_api_key(request: Request):
    value = request.headers.get("X-User-Api-Key")
    if value is None:
        return None
    if not value.strip():
        raise HTTPException(400, "Provide a nonempty Google AI Studio key.")
    return SecretStr(value.strip())


@contextmanager
def provider_errors():
    try:
        with quiet_chat_output():
            yield
    except Exception:
        # Provider exception strings may contain the supplied key. Use a fixed
        # message for quota, billing, authentication, and transport failures.
        raise HTTPException(
            503, "Gemini is busy or the limit was reached; try later or use your own key."
        ) from None


def test_user_key(api_key):
    if api_key is None:
        raise HTTPException(400, "Provide your Google AI Studio key in X-User-Api-Key.")
    with provider_errors():
        model = get_chat_model(api_key)
        model.bind(max_output_tokens=8).invoke("Reply OK.")
    return {"ok": True}

