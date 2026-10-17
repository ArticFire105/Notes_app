# Phase 5: Daily allowance (5/day) + per-answer token limit + BYOK + credit protection

## Context
Phase 4 is done: users log in, roles work.
My server Gemini key is on the PAID tier: billing is enabled, with about $60 in credits. Every call on my key spends real credits, so this phase protects that money.
- Each user gets `QUESTIONS_PER_DAY` (5) questions per day on my key. The day resets at midnight Asia/Dubai.
- Every answer has a per-answer token limit: `MAX_OUTPUT_TOKENS` (already in config) plus `MAX_CONTEXT_TOKENS` (cap on retrieved context sent to Gemini; trim chunks to fit).
- After 5/day, users continue with their OWN Google AI Studio key (BYOK): header `X-User-Api-Key`, used for that request ONLY, never stored server-side, never logged.
- Credit protection on my key: a global daily cap `GLOBAL_DAILY_CAP` (total requests/day on my key for the whole app) and an optional `GLOBAL_DAILY_BUDGET_USD` (stop using my key for the day when today's estimated spend reaches it).
- Track estimated spend: tokens × prices from config `PRICE_INPUT_PER_1M_USD` / `PRICE_OUTPUT_PER_1M_USD`. I fill these from the current Gemini pricing page myself. Don't hard-code any prices. If they're unset (0), show the spend as "unknown" instead of $0.
- Cache: same question + same scope + same documents → return the saved answer without calling Gemini, and don't count it.

## Task
1. `supabase/migrations/0004_usage_cache.sql`:
   - `usage_daily(user_id, day date, requests int, input_tokens int, output_tokens int, est_cost_usd numeric(10,6) default 0, primary key(user_id, day))`. Only server-key calls are recorded here.
   - `answer_cache(id, cache_key text unique, subject_id, module_id, document_id, answer text, sources jsonb, created_at, hits int)`.
   - RLS on both; users can read only their own `usage_daily` rows.
2. `app/quota.py`:
   - `try_consume(user_id) -> bool`: ONE atomic SQL statement:
     `insert ... on conflict (user_id, day) do update set requests = usage_daily.requests + 1 where usage_daily.requests < LIMIT returning requests`. No row returned = over the limit. Comment why one atomic statement beats "select then update" (race condition when two tabs ask at once).
   - `global_ok() -> bool`: today's total requests < `GLOBAL_DAILY_CAP` AND (budget unset OR today's total `est_cost_usd` < `GLOBAL_DAILY_BUDGET_USD`). Comment that this protects my credits if many users ask at once, or if there's a bug/abuse.
   - `estimate_cost(input_tokens, output_tokens) -> Decimal | None` using the config prices (None if unset).
   - `record_usage(user_id, input_tokens, output_tokens)` after the answer: adds the tokens + estimated cost.
   - `remaining(user_id)` for the UI.
   - "Today" = `(now() at time zone 'Asia/Dubai')::date`, computed in SQL.
3. `app/cache.py`: `make_key(question, subject_id, module_id, document_id)` = sha256 of the normalized question (lowercase, trimmed, collapsed spaces) + scope ids. `get` / `put`. `invalidate_scope(subject_id)` runs after any new document ingest in that subject (call it from the ingest pipeline).
4. Per-answer token limit in `app/rag/answer.py`: before calling Gemini, trim the numbered context to `MAX_CONTEXT_TOKENS` (approximate tokens as chars/4 and comment that it's an estimate), and keep `max_output_tokens = MAX_OUTPUT_TOKENS`. This applies to BYOK too (it protects their quota and keeps answers short).
5. Update the `POST /ask` flow (write it as an arrow chain in a comment at the top of the router):
   validate → cache hit? return (nothing counted) → BYOK header? use the user's key (skip my limits) : (`try_consume` AND `global_ok`) or 429 with a friendly message ("You've used your 5 questions for today. Add your own free Google AI Studio key in Settings to keep going.") → retrieve → answer (token-limited) → `record_usage` (only for server-key calls) → cache put → return the answer + `remaining`.
6. `app/llm.py`: `get_chat_model(api_key)` uses the user key when given. Wrap Gemini 429/quota/billing errors into a clear 503 ("Gemini is busy or the limit was reached, try later or use your own key"). Don't assume specific rate-limit numbers.
7. BYOK safety: add a logging filter/middleware that redacts `X-User-Api-Key` and `Authorization` headers from any logs. Add `GET /me/usage` → `{used, limit, resets_at}`. Add an admin-only `GET /admin/usage/today` → `{total_requests, total_input_tokens, total_output_tokens, est_cost_usd or "unknown", global_cap}`.
8. `POST /me/test-key`: makes one tiny Gemini call with the given key to check it works (counts against the user's key, not mine).
9. Tests: `tests/test_quota.py` (limit stops at 5; BYOK skips my limits and records nothing; cache hit doesn't consume; the global cap blocks the server key but not BYOK; cost is None when prices are unset; mock DB where needed), `tests/test_cache.py` (normalization).

Add `QUESTIONS_PER_DAY=5`, `MAX_CONTEXT_TOKENS`, `GLOBAL_DAILY_CAP`, `GLOBAL_DAILY_BUDGET_USD` (empty = off), `PRICE_INPUT_PER_1M_USD`, `PRICE_OUTPUT_PER_1M_USD` to `.env.example`. Comment the price lines: "copy from the current Gemini API pricing page for CHAT_MODEL".

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
