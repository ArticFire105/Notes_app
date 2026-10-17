# Phase 10: Deploy (free hosting) + test with classmates

## Context
Phases 0–9 work locally. Now: deploy the backend + Streamlit for free and run a small test with classmates.
Problem: free hosts with little RAM (e.g. Render free = 512 MB) can't hold the local EmbeddingGemma model. So we add a Gemini embeddings provider and RE-EMBED all chunks with it if needed. Never mix vectors from 2 models in one search.

## Task
1. `app/embeddings.py`: implement the `EMBEDDING_PROVIDER=gemini` branch using `langchain-google-genai` embeddings (or `google-genai` if simpler; tell me which) with model `gemini-embedding-2` (put it in `EMBEDDING_MODEL`), `output_dimensionality=768`. That model doesn't use task_type, so prefix texts like the docs say: queries `"task: search result | query: {q}"`, documents `"title: {title} | text: {chunk}"`. Check the current Gemini embeddings docs and tell me what you used. Normalize vectors.
   Retrieval already filters by `embedding_model`, so old vectors are simply ignored.
2. `scripts/reembed_all.py`: re-embeds every chunk with the current provider in batches, with a progress print, resumable (skips chunks already embedded with the current model), and a `--dry-run` that only counts. It respects the embedding rate limit (sleep between batches, constant at the top) and prints the total tokens so I can estimate the cost (embedding calls on my key spend credits).
3. Deployment files:
   - `Dockerfile` (or Render native Python with uv; pick the simpler one and explain) for the backend: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   - `render.yaml` for the backend service on the free plan. Env vars listed WITHOUT values (I set them in the dashboard).
   - Streamlit deploy notes in `docs/DEPLOY.md` (Streamlit Community Cloud or a second Render service). Frontend gets only `API_BASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.
   - `GET /health` also reports `embedding_provider` and `db: ok` (no secrets).
4. Production hygiene:
   - CORS only if the frontend calls from the browser (Streamlit calls server-side, so explain whether it's needed).
   - Simple per-IP rate limit on `/ask` and upload routes (in-memory is fine for 1 instance; comment the limit).
   - Structured logs: request id, user id, route, latency, tokens. Never keys.
5. `.github/workflows/tests.yml`: run `uv run pytest` on push/PR. No secrets needed (tests mock external calls).
6. `docs/BETA_TEST.md`: a checklist for testing with ~10 classmates first: what to try, a feedback form template (question asked, was the answer right?, were the sources right?, speed 1–5), and what I watch (errors, 429s, questions used per user, estimated Gemini spend from `/admin/usage/today` vs the Google Cloud Billing page, Supabase DB size).
7. `docs/DEPLOY.md`: step-by-step for me: set env vars, deploy, run migrations, run `reembed_all.py` if the provider changed, smoke-test commands with curl, and how to roll back.

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
