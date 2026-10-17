# Phase 3: FastAPI endpoints (list, upload, ask, view PDF)

## Context
Phases 1–2 are done: `ingest_pdf()` and `answer_question()` work from scripts.
Now: wrap them in FastAPI. No auth yet (Phase 4), so this runs on localhost only. Add a big comment at the top of `main.py`: "Do not deploy before Phase 4".
Add these libraries: `fastapi`, `uvicorn[standard]`, `python-multipart`, `supabase` (Python client, for Storage only in this phase).

## Task
1. `app/schemas.py`: Pydantic models: `Subject`, `Module`, `DocumentOut` (id, title, module, page_count, status, created_at), `AskRequest` (question 1–1000 chars, subject_id, module_id optional, document_id optional), `Source`, `AskResponse` (answer, sources, usage).
2. `app/storage.py`: Supabase Storage helpers using the SERVICE ROLE key (backend only):
   `upload_pdf(file_bytes, path)` into a private bucket `notes` with paths like `official/{subject_code}/module-{n}/{uuid}.pdf`, and `signed_url(path, seconds=3600)`.
   Tell me in your reply how to create the private bucket in the dashboard (I'll do it).
3. `app/main.py` + routers in `app/routers/`:
   - `GET /health`
   - `GET /subjects`, `GET /subjects/{id}/modules`, `GET /modules/{id}/documents`
   - `POST /documents` (multipart: file, subject_id, module_id, title): check it's a PDF and under 25 MB → upload to Storage → insert `documents` row with status `processing` → run ingest in FastAPI `BackgroundTasks` → status becomes `ready` or `failed` (+ `error` text). Return the document id right away.
     Change `ingest_pdf` so it can work from an existing document row and bytes (keep the CLI working).
   - `GET /documents/{id}` (to poll status) and `GET /documents/{id}/pdf-url` (returns a signed URL to view the raw PDF).
   - `POST /ask` → `answer_question()` → `AskResponse`.
4. Load the embedding model ONCE at startup (FastAPI lifespan), not per request. Comment why.
5. Errors: clear `HTTPException` messages (404 unknown subject/module, 400 bad file). Never return stack traces to the client.
6. Add a migration `supabase/migrations/0002_documents_status.sql` only if the `documents` table needs new columns (`status`, `error`, `storage_path`). Check 0001 first.
7. `tests/test_api.py` with FastAPI `TestClient`: `/health` works, `/ask` rejects an empty question (422). Mock `answer_question` so the test needs no DB or Gemini.

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
