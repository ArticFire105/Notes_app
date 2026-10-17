# Lecture Notes RAG

An open-source lecture-notes app for about 100 CSE students at Manipal Dubai.
The goal is answers grounded in department notes, with sources for each answer.
Phase 0 provides configuration, database SQL, and setup checks only.

Stack: Python 3.12 + uv; Supabase Postgres, pgvector, Auth, and Storage;
local EmbeddingGemma embeddings; Gemini `gemini-3.5-flash-lite`.
FastAPI and the Streamlit UI come in later phases.

## How to run locally

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
   from the repository root:

   ```powershell
   uv sync
   ```

2. **Manually** copy `.env.example` to `.env` and replace the placeholders.
   The comment above each setting explains where to find it. Never commit `.env`.
   Use the Supabase **Connect > Session pooler** connection string with your
   database password and a trusted database role (the default `postgres` role).
   Keep `sslmode=require`. Set a Hugging Face read token and accept the model's
   access terms on Hugging Face if required.

3. In the Supabase **SQL Editor**, run
   [0001_init.sql](supabase/migrations/0001_init.sql), then
   [seed.sql](supabase/seed.sql). Run the migration once. The seed can be rerun;
   it preserves renamed module titles. It creates five subjects and modules 1–5
   for each subject (25 modules). Rename the placeholder titles yourself.
   RLS is enabled with no policies, so direct client access is denied. The
   database connection must use a role that bypasses RLS.

4. Run the offline tests, then the live setup check:

   ```powershell
   uv run pytest
   uv run python scripts/check_setup.py
   ```

   Tests use dummy settings with `.env` loading disabled, mock external calls,
   and do not download models. The live check reads your settings, queries
   pgvector and the five subjects, and loads the embedding model to check a
   test vector has 768 dimensions. The first model load may download weights
   and take time. It makes no Gemini calls or database writes. A failed check
   exits with status 1; all checks passing exits with status 0.
   Error output is deliberately generic to avoid exposing credentials.

Model identifiers are taken from [the project plan](docs/PROJECT_PLAN.md).
The live check will report failure if the configured model cannot be accessed
or does not produce 768 dimensions; it does not silently substitute a model.

Read [AGENTS.md](AGENTS.md) before contributing. Licensed under [MIT](LICENSE).
