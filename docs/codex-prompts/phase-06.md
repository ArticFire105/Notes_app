# Phase 6: Streamlit UI (matches the app vision)

## Context
Phases 1–5 are done: the FastAPI backend has auth, quota, BYOK, cache, upload, ask, and PDF URLs.
Now: a Streamlit frontend that ONLY talks to the FastAPI backend over HTTP. It never touches the DB or the service-role key.
Add the libraries `streamlit` and `httpx`.

## Task
Create `frontend/`:
1. `frontend/api_client.py`: small functions wrapping each backend endpoint with `httpx`. Base URL from `API_BASE_URL` (add it to `.env.example`). Attach `Authorization` from `st.session_state["access_token"]`, and `X-User-Api-Key` if the user saved a key in session. Turn backend errors into friendly messages.
2. `frontend/app.py` using `st.navigation` / multipage:
   - **Login page:** email → "Send code" → 6-digit code → verify with Supabase (anon key, via `supabase` client) → store access + refresh tokens in `st.session_state` only. Show an error for non-college emails.
   - **Home:** 5 subject cards in a grid (OS, SE, POC, CN, EOM) (code, full name, number of modules). Clicking opens the subject page.
   - **Subject page:** list modules; under each, its PDFs with a "View PDF" button (signed URL from the backend, opens in a new tab).
     A scope selector: `This PDF` / `This module` / `Whole subject` (default: the selected module).
     A chat box (`st.chat_input` + `st.chat_message`), with history kept in `st.session_state` per subject.
     Each answer shows a "Sources" expander: `[1] OS · Module 2 · Memory.pdf · p.14 (score 0.82)`.
     Show "questions left today: X/5" near the chat (after that: use your own key).
   - **Settings:** usage today; a "Use your own key" box (password input), with a link to https://aistudio.google.com/apikey and short steps ("sign in → Create API key → paste here"). A "Test key" button calls `/me/test-key`. The key lives only in `st.session_state` and is gone when the tab closes; say so in the UI. Also show a short note: "Free AI Studio keys: Google may use your content to improve its products (see Google's terms). Don't upload personal info." "Other providers: coming later."
   - **Admin upload** (only visible if `/me` says admin): pick subject + module, title, file → upload → poll status until ready/failed.
   - Placeholder pages "My handwritten notes", "Past papers", "Quiz" that say "coming soon" (later phases fill them in).
3. Keep each page in its own file under `frontend/pages/`. No custom CSS beyond a few lines.
4. README: how to run both: `uv run uvicorn app.main:app --reload` and `uv run streamlit run frontend/app.py`.

No new backend features in this phase, except tiny read endpoints the UI truly needs (tell me if you add one).

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
