"""Verify the prerequisites at the end of the Phase 0 setup flow.

Run this manually from the repository root after filling settings.
Apply the migration and seed yourself in the Supabase SQL Editor.
This script never applies migrations or inserts application data.

Settings are loaded first so missing configuration fails early.
Database and embedding checks run independently after settings load.
A failed database check does not hide a separate embedding failure.
The process returns zero only when every check passes.
The database connection uses the supplied trusted backend URL.
A connection timeout keeps an unreachable database from waiting forever.
The first query reports the installed pgvector extension version.
The second query reads the public subject codes and names.
Exactly five rows with the planned codes must exist.

The embedding check loads the configured local model once.
The Hugging Face token is unwrapped only for the model constructor.
The first invocation may download weights into the normal model cache.
A short test sentence exercises the actual embedding output.
The output must match the database's 768-dimensional vector column.

This phase does not generate answers or call Gemini.
It does not upload files or build a retrieval pipeline.
Model failures leave the configured model choice unchanged.
Third-party progress and error output are suppressed around model loading.

Raw exception messages might contain credentials or authenticated URLs.
Failures therefore print fixed guidance instead of exception details.
Only public database results and vector dimensions are printed.
The previous logging threshold is restored after the model check.

Offline tests replace database and model libraries with test doubles.
Both direct script execution and module execution are supported.
"""

from contextlib import redirect_stderr, redirect_stdout
import logging
import os
from pathlib import Path
import sys

# Support both a direct script invocation and python -m scripts.check_setup.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings


EXPECTED_CODES = {"OS", "SE", "POC", "CN", "EOM"}


def check_database(settings: Settings) -> bool:
    try:
        import psycopg

        with psycopg.connect(
            settings.database_url.get_secret_value(), connect_timeout=10
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select extversion from pg_extension where extname = 'vector'"
                )
                vector_version = cursor.fetchone()
                cursor.execute("select code, name from subjects order by code")
                subjects = cursor.fetchall()
    except Exception:
        # Database exceptions can contain a connection string or password.
        print("FAIL database: check DATABASE_URL and run both SQL files manually.")
        return False

    vector_ok = vector_version is not None
    print(
        f"PASS pgvector: {vector_version[0]}"
        if vector_ok else "FAIL pgvector: extension is not installed."
    )
    for code, name in subjects:
        print(f"Subject: {code} - {name}")
    subjects_ok = len(subjects) == 5 and {row[0] for row in subjects} == EXPECTED_CODES
    print(
        "PASS subjects: exactly OS, SE, POC, CN, EOM."
        if subjects_ok else "FAIL subjects: expected exactly OS, SE, POC, CN, EOM."
    )
    return vector_ok and subjects_ok


def check_embedding(settings: Settings) -> bool:
    print("Checking local embeddings (the first run may download model weights)...")
    previous_logging_level = logging.root.manager.disable
    try:
        # Third-party download errors can include authenticated URLs. Keep their
        # output private and provide a fixed diagnostic instead of a traceback.
        with open(os.devnull, "w") as quiet:
            with redirect_stdout(quiet), redirect_stderr(quiet):
                logging.disable(logging.CRITICAL)
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    settings.embedding_model,
                    token=settings.hf_token.get_secret_value(),
                )
                vector = model.encode(
                    "Lecture notes setup check.", show_progress_bar=False
                )
                dimension = len(vector)
    except Exception:
        print("FAIL embeddings: check model access, HF_TOKEN, downloads, and local memory.")
        return False
    finally:
        logging.disable(previous_logging_level)

    passed = dimension == settings.embedding_dim == 768
    print(f"{'PASS' if passed else 'FAIL'} embeddings: {dimension} dimensions (expected 768).")
    return passed


def main() -> int:
    try:
        settings = Settings()
    except Exception:
        # Even settings validation can expose inputs if its raw error is printed.
        print("FAIL settings: fill .env using .env.example; local embeddings must use 768 dimensions.")
        return 1
    print("PASS settings: required values loaded.")
    database_ok = check_database(settings)
    embedding_ok = check_embedding(settings)
    return 0 if database_ok and embedding_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
