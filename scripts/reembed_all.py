"""
Re-embed stored chunks with the configured Gemini embedding model.
This script is run once during the embedding model migration.
It covers official document chunks and private note chunks.
It does not read source files from Storage.
It reads existing chunk text from Postgres.
It never prints chunk text or credentials.
Gemini receives the existing chunk text for embedding.
The server key is taken from the existing settings.
The user must configure the Gemini provider and model.
The target vector dimension stays at 768.
The database schema therefore does not need a migration.
The embedding model label is updated with each vector.
Each batch is committed independently.
A failed batch is rolled back.
Rerunning skips chunks already using the target model.
This allows an interrupted migration to resume.
The script processes small batches to limit API requests.
The shared embedding client handles retries and pacing.
Counts are printed without any private content.
The dry-run option counts without calling Gemini.
Cached answers are invalidated after each official batch.
Personal answers do not use the shared answer cache.
The backend should be stopped during the migration.
This prevents users seeing incomplete search results.
It also prevents concurrent edits during re-embedding.
The script never deletes a chunk or its source file.
Database credentials remain in the settings object.
Raw database and provider exceptions are not printed.
A failure produces a fixed diagnostic message.
A successful run prints the number of rows changed.
Google API calls can incur charges.
Run the dry run first to see the number of chunks.
Use the same model setting when restarting the backend.
Tests can replace database and embedding functions.
Run it from the project root with uv run.
"""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pgvector import Vector
from app.cache import invalidate_scope
from app.config import Settings
from app.db import get_conn
from app.embeddings import embed_documents

BATCH_SIZE = 32
TABLES = ("chunks", "personal_note_chunks")


def migrate_table(table, model, dry_run=False):
    if table not in TABLES:
        raise ValueError("Unknown table")
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"select count(*) from {table} where embedding_model is distinct from %s", (model,))
            remaining = cursor.fetchone()[0]
    print(f"{table}: {remaining} chunks need re-embedding")
    if dry_run:
        return 0
    done = 0
    while True:
        with get_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select id, subject_id, content from {table} where embedding_model is distinct from %s order by id limit %s", (model, BATCH_SIZE))
                rows = cursor.fetchall()
                if not rows:
                    break
                vectors = embed_documents([row[2] for row in rows])
                for (chunk_id, subject_id, content), vector in zip(rows, vectors, strict=True):
                    cursor.execute(f"update {table} set embedding = %s, embedding_model = %s where id = %s and content = %s and embedding_model is distinct from %s", (Vector(vector), model, chunk_id, content, model))
                    if cursor.rowcount != 1:
                        raise RuntimeError("Chunk changed during migration")
                if table == "chunks":
                    for subject_id in {row[1] for row in rows}:
                        invalidate_scope(subject_id, cursor)
        done += len(rows)
        print(f"{table}: {done} / {remaining} chunks re-embedded")
    return done


def main():
    parser = argparse.ArgumentParser(description="Re-embed stored chunks with Gemini.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings()
        if settings.embedding_provider != "gemini" or settings.embedding_model != "gemini-embedding-2" or settings.embedding_dim != 768:
            raise ValueError("Incorrect embedding configuration")
        for table in TABLES:
            migrate_table(table, settings.embedding_model, args.dry_run)
    except Exception:
        print("Re-embedding stopped. Check Gemini and database configuration, then rerun.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
