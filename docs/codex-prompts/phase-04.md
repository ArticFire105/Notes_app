# Phase 4: Login (Supabase Auth) + roles + college email only

## Context
Phase 3 is done: FastAPI has list/upload/ask endpoints with no auth.
Now: only `@dxb.manipal.edu` users can use the app. Only `admin` can upload. Roles: `student` (default), `rep` (later), `admin`.
Login method: Supabase email OTP (6-digit code), because it works easily in Streamlit later (no redirect handling).

## Task
1. `supabase/migrations/0003_profiles_roles.sql`:
   - `profiles` table (see plan schema): `id uuid primary key references auth.users on delete cascade`, `email`, `full_name`, `role text not null default 'student' check (role in ('student','rep','admin'))`, `year int`, `school text`, `created_at`.
   - Trigger function `handle_new_user()` (security definer, `set search_path = ''`) that inserts a profile row when a row is added to `auth.users`.
   - Add the FK `documents.uploaded_by → profiles(id)`.
   - RLS: enable on `profiles`; policy "users can read their own profile". No client-side writes to `role` (only I change roles, via SQL).
   - Read-only RLS policies for authenticated users on `subjects`, `modules`, and `documents` where `source_type in ('official','past_paper')`. Comment that the backend's DB connection bypasses RLS, so RLS is the safety net, not the main check.
   - A commented line showing how I make myself admin: `update public.profiles set role='admin' where email='...';`
2. `app/auth.py`:
   - `get_current_user` FastAPI dependency: read `Authorization: Bearer <access_token>`, verify it with Supabase (`supabase.auth.get_user(token)`, simplest and correct), then load the profile row. 401 if missing/invalid.
   - Reject (403) any email not ending in `@` + `settings.ALLOWED_EMAIL_DOMAIN` (add `ALLOWED_EMAIL_DOMAIN=dxb.manipal.edu` to `.env.example`). Lowercase before comparing.
   - `require_role(*roles)` dependency factory.
   - A tiny in-memory cache (token → user, 60 s) so we don't call Supabase on every request. Comment the trade-off.
3. Protect routes: every route except `/health` needs a logged-in user; `POST /documents` needs `admin`. Set `documents.uploaded_by` from the user.
4. `GET /me` returns `{email, role}`.
5. `scripts/get_token.py` (dev only): asks for my email, sends the OTP with the Supabase anon key, asks me to type the code, prints ONLY the access token so I can test with curl. Add a warning comment: never paste tokens anywhere public.
6. `tests/test_auth.py`: unit-test the domain check (good, bad, uppercase, sneaky `user@dxb.manipal.edu.evil.com`). Mock Supabase.

Remove the "Do not deploy" comment from `main.py` only after auth is in place.

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
