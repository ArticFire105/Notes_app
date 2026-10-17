# Phase 0: Repo + Supabase + env setup

## Context
We're building an open-source lecture-notes RAG app for my CSE department (~100 students, Manipal Dubai).
Stack: Python + uv, FastAPI (later), Supabase (Postgres + pgvector + Auth + Storage), local EmbeddingGemma embeddings, Gemini `gemini-3.5-flash-lite`, Streamlit UI (later).
The full plan is in `docs/PROJECT_PLAN.md`. This phase only sets up the skeleton. No RAG code yet.

## Task
1. Set up a uv project at the repo root (`pyproject.toml`, Python 3.12). Add these dependencies:
   `psycopg[binary]`, `pgvector`, `pydantic-settings`, `pypdf`, `langchain-text-splitters`, `langchain-huggingface`, `sentence-transformers`, `langchain`, `langchain-google-genai`. Dev: `pytest`.
2. Create this folder skeleton (empty `__init__.py` where needed): `app/`, `app/ingest/`, `app/rag/`, `scripts/`, `tests/`, `supabase/migrations/`, `docs/`, `data/` (gitignored).
3. `.gitignore`: `.env`, `.venv/`, `data/`, `__pycache__/`, `*.pdf`, `.ipynb_checkpoints/`, model caches.
4. `.env.example` with placeholders only:
   `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_API_KEY`, `HF_TOKEN`,
   `EMBEDDING_PROVIDER=local`, `EMBEDDING_MODEL=google/embeddinggemma-2`, `EMBEDDING_DIM=768`, `CHAT_MODEL=google_genai:gemini-3.5-flash-lite`.
   Add a one-line comment above each saying where to find it (e.g. DATABASE_URL = Supabase "Connect" → Session pooler string).
5. `app/config.py`: one `Settings` class (pydantic-settings) that reads `.env`. Secrets typed as `SecretStr` so they never print by accident.
6. `supabase/migrations/0001_init.sql`:
   - `create extension if not exists vector;`
   - tables `subjects`, `modules`, `documents`, `chunks` exactly as in the "Database schema" section of `docs/PROJECT_PLAN.md` (Phase 0 part only; no profiles/usage/quiz yet).
   - indexes: HNSW on `chunks.embedding` with `vector_cosine_ops`, and a btree on `chunks (subject_id, module_id, source_type)`.
   - `alter table ... enable row level security;` on every table (no policies yet; backend connects with the DB URL so it isn't blocked).
   - Comment each table and column group with WHY it exists.
7. `supabase/seed.sql`: insert the 5 subjects (`OS` Operating Systems, `SE` Software Engineering, `POC` Principles of Cryptography, `CN` Computer Networks, `EOM` Essentials of Management) and placeholder modules 1–5 for each (25 modules total) (titles "Module N" that I will rename).
8. `scripts/check_setup.py`: a script that
   - loads settings,
   - connects to Postgres and prints the pgvector version and the subject list (FAIL if it isn't exactly the 5 codes OS, SE, POC, CN, EOM),
   - loads the embedding model and prints the length of one test vector (should be 768),
   - prints PASS/FAIL per check, and never prints any secret.
9. `AGENTS.md` at the root: copy the "Rules for you, Codex" section below, plus "run tests with `uv run pytest`".
10. `README.md`: short project intro, stack, "how to run locally" (uv sync, fill .env, run SQL in Supabase SQL editor, run check_setup). Add an MIT `LICENSE`.

I will run the SQL files in the Supabase SQL editor myself. Don't try to connect to Supabase or run migrations for me.

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
