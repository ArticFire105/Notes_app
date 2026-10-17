# Phase 1: Minimal ingest (one PDF → chunks → vectors → pgvector)

## Context
Phase 0 is done: the uv project, `app/config.py`, and tables `subjects`, `modules`, `documents`, `chunks` (with `embedding vector(768)`) exist in Supabase.
Now: a command-line script that ingests ONE PDF for a given subject + module. No API, no UI, no auth.

## Task
1. `app/db.py`: a `get_conn()` helper using `psycopg` + `pgvector.psycopg.register_vector` and `settings.DATABASE_URL`. Use a context manager so connections always close.
2. `app/embeddings.py`: one place for embeddings.
   - `get_embedder()` returns a cached LangChain `HuggingFaceEmbeddings` for `settings.EMBEDDING_MODEL`:
     `model_kwargs={"device": "cpu", "config_kwargs": {"vision_config": None, "audio_config": None}}` (text-only, saves RAM),
     `encode_kwargs={"prompt_name": "Retrieval-document", "normalize_embeddings": True}`,
     `query_encode_kwargs={"prompt_name": "Retrieval-query", "normalize_embeddings": True}`.
     Check the model card for the exact prompt names. If they differ, use the card's names and tell me.
   - `embed_documents(texts) -> list[list[float]]` and `embed_query(text) -> list[float]`.
   - Assert every vector has length `settings.EMBEDDING_DIM`.
   - Leave a clear `if settings.EMBEDDING_PROVIDER == "gemini":` branch with `NotImplementedError` and a comment: "Phase 10 fallback for low-RAM hosts".
3. `app/ingest/pdf_loader.py`: `load_pdf_pages(path) -> list[dict]` using `pypdf`, returning `{"page": 1-based int, "text": str}` per page. Skip pages with almost no text, but COUNT them and return the count too (a scanned PDF has no text; we handle that in Phase 7).
4. `app/ingest/chunker.py`: `chunk_pages(pages)` using `RecursiveCharacterTextSplitter` (chunk_size≈1000 chars, overlap≈150, put both in constants at the top). Chunk page by page so every chunk keeps its page number. Return `{"page", "chunk_index", "content"}`.
5. `app/ingest/pipeline.py`: `ingest_pdf(path, subject_code, module_number, title, source_type="official") -> document_id`
   load → chunk → embed in batches of 32 → in ONE transaction insert a `documents` row (status `ready`, page_count) and all `chunks` rows (with subject_id, module_id, source_type, page, chunk_index, content, embedding, embedding_model). If anything fails, roll back and leave nothing half-inserted.
   Before inserting, check whether a document with the same title already exists for that module. If it does, refuse unless `replace=True`, which deletes the old document (its chunks cascade).
6. `scripts/ingest_pdf.py`: CLI with argparse: `--pdf`, `--subject OS`, `--module 2`, `--title "Memory Management"`, `--replace`. Print a short summary: pages read, pages skipped (no text), chunks stored, seconds taken.
7. `tests/test_chunker.py`: tests that chunks keep correct page numbers and that none are empty. No DB, no model needed.

Don't upload the PDF to Supabase Storage yet (Phase 3). Don't write retrieval yet (Phase 2).

## Rules for you, Codex (read every time)
- I'm a student learning AI engineering by building this. I read every line you write.
- Keep code simple: small functions, clear names, no clever tricks, no extra abstraction layers.
- Comment the WHY (not the obvious what). Put a 3–5 line docstring at the top of each new file saying what it does and where it sits in the flow.
- Do ONLY this phase. When it's done, STOP. Don't start the next phase or add "nice to have" features.
- Never open, read, print, create or edit `.env` or any real secret. If you need a new setting, add it to `.env.example` with a placeholder value and tell me to fill `.env` myself.
- Never log or print API keys, tokens or passwords, even partly.
- Use only the libraries listed in this prompt (plus the standard library). If you think you need another one, ask me first.
- Follow `AGENTS.md` and `docs/PROJECT_PLAN.md` in the repo.
- When finished, reply with:
  1. Files created/changed, one line each on why.
  2. The flow of this phase as an arrow chain (a → b → c).
  3. Exact commands for me to test it.
  4. Anything you weren't sure about or skipped.
