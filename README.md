# Lecture Notes RAG

An open-source lecture-notes app for about 100 CSE students at Manipal Dubai.
The goal is answers grounded in department notes, with sources for each answer.
Phase 0 provides configuration and database setup; Phase 1 adds local PDF ingestion.

Stack: Python 3.12 + uv; Supabase Postgres, pgvector, Auth, and Storage;
local EmbeddingGemma embeddings; Gemini `gemini-3.5-flash-lite`.
FastAPI serves the backend; Streamlit provides the Phase 6 UI.

The current frontend is the Next.js App Router app in `web/`. The older
Streamlit `frontend/` folder is retained. See [web/README.md](web/README.md)
for Node installation, startup commands, and the manual UI checklist.

Current uploads support PDF and PowerPoint (`.pptx`) up to 40 MB in FastAPI
and the Next.js admin screen. PowerPoint slide text and speaker notes use the
shared ingestion pipeline and retain **Slide N** citations. Save old `.ppt`
files as `.pptx` before uploading. See the web README for Storage settings.

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

## Ingest one PDF (Phase 1)

After completing setup, put a text-based PDF in the ignored `data/` directory:

```powershell
uv run python scripts/ingest_pdf.py --pdf data/os_module2.pdf --subject OS --module 2 --title "Memory Management"
```

The script extracts text page by page, skips pages with fewer than 20
non-whitespace characters, makes 1000-character chunks with 150-character
overlap, and embeds batches of 32 on the CPU. The summary includes all PDF
pages read, skipped pages, stored chunks, and elapsed seconds. Entirely scanned
PDFs fail with their skipped-page count; OCR comes in Phase 7.

EmbeddingGemma uses the `Document` and `SearchQuery` prompts from its
[model card](https://huggingface.co/google/embeddinggemma-2#quick-start), with
vision and audio encoders disabled and normalized 768-dimensional vectors.
The model is cached in the process; the first invocation may download weights.
The Gemini embedding provider is an explicit unimplemented Phase 10 fallback.

A matching title within the module is refused. Add `--replace` to replace it:

```powershell
uv run python scripts/ingest_pdf.py --pdf data/os_module2.pdf --subject OS --module 2 --title "Memory Management" --replace
uv run pytest
```

Embeddings finish before any database writes. Duplicate checking and all writes
run in one transaction, with a module lock to serialize simultaneous uploads.
A failed replacement restores the old document and its chunks. No PDF is uploaded
to Storage in this phase, so `storage_path` remains empty.

Read [AGENTS.md](AGENTS.md) before contributing. Licensed under [MIT](LICENSE).

## Login and roles (Phase 4)

All API endpoints except `/health` now require a verified Supabase bearer token
and a college email. Only an `admin` can upload official PDFs. The backend reads
the role from `profiles` on every request; role changes take effect immediately.
Token verification is cached for up to 60 seconds, never beyond token expiry.
A revoked token can therefore continue working for up to 60 seconds.
Interactive API documentation is disabled by default and in production.
For local development, explicitly set `APP_ENV=development` in your shell
before starting the server; `/docs` and `/openapi.json` will then be available.
`/redoc` remains disabled. This switch uses the process environment directly,
so adding it only to `.env` does not enable documentation.

```powershell
$env:APP_ENV = 'development'
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`, click **Authorize**, and paste the access token
without the `Bearer ` prefix. API routes still require authentication.
Swagger does not persist authorization across page reloads. For production,
leave `APP_ENV` unset or set it to `production`, then restart the server.

Complete these steps by hand in Supabase:

1. Run [0003_profiles_roles.sql](supabase/migrations/0003_profiles_roles.sql)
   once in the SQL Editor, after `0001_init.sql`. It also creates profiles for
   existing Auth users. Confirm RLS is enabled on all five public application
   tables. The backend must keep using a trusted database connection.
2. Under Authentication, enable the Email provider and allow new signups if
   students should create accounts through OTP login. In the Magic Link email
   template, include `{{ .Token }}` to send a code instead of a link.
   See [Supabase's OTP instructions](https://supabase.com/docs/guides/auth/auth-email-passwordless).
3. Configure custom SMTP before testing with addresses outside your Supabase
   project team. The built-in sender only sends to team addresses and has a
   low sending limit. See [Supabase's SMTP restrictions](https://supabase.com/docs/guides/auth/auth-smtp).
4. Run the backend and OTP helper below. Confirm a profile appears with role
   `student`. In the SQL Editor, replace the placeholder and run:

   ```sql
   update public.profiles set role = 'admin'
   where email = 'YOUR_EMAIL@dxb.manipal.edu';
   ```

The new `ALLOWED_EMAIL_DOMAIN=dxb.manipal.edu` setting is in `.env.example`.
It is also the default; add it to your own local configuration if desired.
Never share credentials or tokens.

Run the offline tests:

```powershell
uv run pytest
```

Start the API in one terminal:

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, check public health, rejected anonymous access, then OTP:

```powershell
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i http://127.0.0.1:8000/subjects
uv run python scripts/get_token.py
```

Expect 200 for health, 401 for anonymous subjects, and email plus role after
successful OTP login. Run the helper again after promotion to see `admin`.
The helper keeps its token in memory and calls `/me` itself by default.
For manual API testing, `uv run python scripts/get_token.py --print-token`
explicitly prints the token after login instead of calling `/me`. Never paste
tokens publicly. `/docs` is available only with `APP_ENV=development`.
Offline tests cover invalid tokens, domain lookalikes, student/rep upload
rejection, administrator upload attribution, and cache expiry.

Live OTP delivery, trigger execution, and RLS must be checked in your own
Supabase project; the offline suite mocks external services.

## Quota, BYOK, and cache (Phase 5)

The request flow is: authenticate → validate scope → cache → BYOK or reserve
server allowance → retrieve → trim context → Gemini → record usage → cache
successful answers → return remaining questions.

The default allowance is five server-key questions per user per Dubai day.
`GET /me/usage` returns `{used, limit, resets_at}`; `resets_at` is the next
midnight in Dubai. `/ask` also returns `remaining`. Cache hits return zero
token usage and spend no allowance. BYOK skips the server's personal and
global limits and is never written to the usage ledger. Keys are accepted
only in the `X-User-Api-Key` request header and are never stored.

Only successful answers with sources are cached. Empty answers, responses
containing "not found" (case insensitive), and errors are excluded. Uploading
or replacing notes clears that subject's cache in the publishing transaction.
Keys also include the ready official document IDs, so a generation that overlaps
an upload cannot make an old answer reusable for the new document set.

Request reservations are atomic. A database transaction lock coordinates the
global cap check and reservation across backend processes. Empty retrieval
returns its reservation because no Gemini call occurred. Failed requests keep
their reservation conservatively: a provider failure does not prove that no
billable work happened. A generated "Not found" response still consumes a
question and records tokens, but is never cached.

`MAX_CONTEXT_TOKENS` estimates retrieved context as characters divided by four;
it includes numbered source headings but excludes the question and system
prompt. `MAX_OUTPUT_TOKENS` limits the answer. Both apply to BYOK as well.
The CLI answer helper shares these token limits; HTTP quota/cache enforcement
belongs to `/ask`, so the trusted local CLI is not a metered student entrypoint.

Complete these steps by hand:

1. Run [0004_usage_cache.sql](supabase/migrations/0004_usage_cache.sql) once in
   the Supabase SQL Editor, after `0003_profiles_roles.sql`. Confirm RLS is
   enabled on both new tables. Direct authenticated clients may select only
   their own usage; the shared cache is accessible only through the backend.
2. Copy the six Phase 5 settings from `.env.example` into your own `.env`
   yourself. Choose `QUESTIONS_PER_DAY`, `MAX_CONTEXT_TOKENS`, and
   `GLOBAL_DAILY_CAP`. Leave `GLOBAL_DAILY_BUDGET_USD` empty to disable the
   estimated spend budget, or set a positive amount.
3. Check current Gemini pricing for your `CHAT_MODEL` and fill both
   `PRICE_INPUT_PER_1M_USD` and `PRICE_OUTPUT_PER_1M_USD` yourself before paid
   testing. Zero means unknown, and `/admin/usage/today` displays `"unknown"`.
   A configured dollar budget with unknown prices blocks server-key requests;
   BYOK remains available. Costs already recorded with unknown prices are not
   backfilled when prices change.
4. In Google Cloud Billing, configure budget alerts for the project behind
   your Gemini key. Check that project's current rate limits in AI Studio.
   Alerts send notifications; the application request cap stops new server-key
   calls. The dollar budget uses completed-call estimates, so calls already
   in flight may overshoot it. Estimates are not exact billing totals.
5. Restart the backend after changing your settings. Run the offline tests and
   the manual checks below. No migration or live model call was run by Codex.

Run all tests, or just the new coverage:

```powershell
uv run pytest
uv run pytest tests/test_quota.py tests/test_cache.py
```

Start the backend:

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For manual API checks, obtain a session access token privately through your
own Supabase login. `scripts/get_token.py --print-token` can print one for manual
testing; without the flag it checks login without printing a token.
Never paste a token or key into chat or literal commands.
In a second PowerShell terminal, enter your token through hidden input:

```powershell
$phase5Token = [System.Net.NetworkCredential]::new('', (Read-Host 'Supabase access token' -AsSecureString)).Password
$phase5Headers = @{ Authorization = "Bearer $phase5Token" }
Invoke-RestMethod http://127.0.0.1:8000/me/usage -Headers $phase5Headers
Invoke-RestMethod http://127.0.0.1:8000/admin/usage/today -Headers $phase5Headers
```

The admin endpoint must return 403 for a student and today's totals for an
administrator. Pick a real subject ID and a question answered in its notes:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/subjects -Headers $phase5Headers
$phase5Body = @{ question = 'What is paging?'; subject_id = 1 } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/ask -Method Post -Headers $phase5Headers -ContentType 'application/json' -Body $phase5Body
Invoke-RestMethod http://127.0.0.1:8000/ask -Method Post -Headers $phase5Headers -ContentType 'application/json' -Body $phase5Body
Invoke-RestMethod http://127.0.0.1:8000/me/usage -Headers $phase5Headers
```

The second supported answer should have zero token usage and leave `used`
unchanged. Ask six distinct supported questions with a fresh day's allowance:
the sixth should return 429. Repeated unsupported questions must not add cache
rows; generated not-found responses can still spend tokens. Upload a new PDF
and confirm that subject's old cache rows are deleted.

Test BYOK with another hidden input (the key test spends a tiny user-key call):

```powershell
$phase5UserKey = [System.Net.NetworkCredential]::new('', (Read-Host 'Your Google AI Studio key' -AsSecureString)).Password
$phase5Headers['X-User-Api-Key'] = $phase5UserKey
Invoke-RestMethod http://127.0.0.1:8000/me/test-key -Method Post -Headers $phase5Headers
Invoke-RestMethod http://127.0.0.1:8000/ask -Method Post -Headers $phase5Headers -ContentType 'application/json' -Body $phase5Body
Invoke-RestMethod http://127.0.0.1:8000/me/usage -Headers $phase5Headers
Remove-Variable phase5Headers, phase5Token, phase5UserKey
```

Use a new supported question for BYOK to prove it calls the provider rather
than returning a cache hit. It should work after the personal or global cap,
without increasing server usage. A bad key should produce a fixed 503 response.
Check logs contain neither keys nor access tokens.

In Supabase SQL Editor, inspect daily usage and successful cache entries:

```sql
select day, sum(requests), sum(input_tokens), sum(output_tokens), sum(est_cost_usd)
from public.usage_daily group by day order by day desc;
select subject_id, hits, created_at from public.answer_cache;
```

For a disposable test user, move its usage row to an unused earlier day and
confirm today's allowance resets. Temporarily set `GLOBAL_DAILY_CAP=1`, restart,
and use distinct supported questions to check the shared cap; restore your
chosen setting afterward. Also test a small positive dollar budget with known
prices. Compare estimated spend with the Google Cloud Billing page later.
Live RLS, timezone rollover, and database concurrency checks remain manual;
offline tests check the SQL structure and request behavior with service doubles.

## Streamlit UI (Phase 6)

Install dependencies from the repository root:

```powershell
uv sync
uv run pytest
```

Start FastAPI in terminal 1:

```powershell
uv run uvicorn app.main:app --reload
```

Start Streamlit in terminal 2:

```powershell
$env:API_BASE_URL = 'http://127.0.0.1:8000'
uv run streamlit run frontend/app.py
```

Open http://localhost:8501. The frontend reads only `API_BASE_URL` from the
process environment, with the local backend URL as its default. It does not
load `.env`, import backend settings, connect to Postgres, or use a Supabase
key. Do not give the frontend database or service role credentials.
`.env.example` documents the new setting; set it in the frontend shell.

The phase prompt proposed direct Supabase login. To honor the backend-only
frontend boundary, FastAPI now proxies login with the existing anon key:
`POST /auth/send-code`, `POST /auth/verify`, and `POST /auth/refresh`.
These are the only new backend routes. Each Supabase client disables session
persistence and automatic refresh. Token responses have `Cache-Control: no-store`.
Streamlit refreshes expiring sessions through FastAPI and keeps rotated tokens
only in `st.session_state`. No database migration is needed for Phase 6.

Complete these steps by hand before live testing:

1. Finish the Phase 4 and 5 Supabase migrations and backend configuration if
   not already done. Keep real credentials in your backend configuration only.
2. Enable email OTP in Supabase, configure SMTP for college users, and include
   `{{ .Token }}` in the email template. Set OTP length to **6 digits** to match
   this screen. Sending codes is subject to your project's email rate limits.
3. For upload testing, promote your own profile to `admin` as described above.
   The existing private `notes` Storage bucket must be configured. The backend
   embedding model must already be accessible.
4. Run the installation, tests, and two server commands above.

Walk through the UI:

- Reject a noncollege email. Log in with a college email and its emailed code.
- Check the five seeded subject cards and module counts. Open OS, expand Module 2,
  obtain a PDF link, then click **View PDF** to open the signed link in a new tab.
  If older CLI-ingested documents have no stored PDF, upload one through the UI.
- Ask a question with **This module** (the default), **This PDF**, and
  **Whole subject**. Verify document names, module numbers, pages, and scores
  in Sources. Switch subjects and confirm their chats stay separate.
- Check that remaining questions update after successful calls. Repeated cached
  answers should leave the allowance unchanged. At the daily limit, add your
  own key in Settings to continue; shared/global limits may also return 429.
- In Settings, follow the AI Studio link, paste a key into the password box,
  and click **Test key**. This makes a small billable call using that key.
  Navigate away and back: the key should still work. Remove it and verify it
  is cleared. Refresh the tab or log out: both tokens and the key should clear.
- As an admin, upload a text PDF under 25 MB and watch status refresh every
  three seconds until ready or failed. A backend restart can interrupt the
  existing in-process ingestion task; polling does not restart ingestion.
- Log in as a student: Admin upload must be absent. Notes, Past papers, and
  Quiz should show **Coming soon**.

Tokens, keys, widget values, and per-subject chats are session-only and are
cleared on logout. Refreshing the page starts a new Streamlit session.
FastAPI remains responsible for domain validation, roles, quota, and retrieval.
Offline tests mock HTTP and Supabase, exercise Streamlit screens, and make no
live email, database, Storage, model-download, or Gemini calls. Live email
delivery, signed PDF links, ingestion, and answer quality must be tested by hand.
# Handwriting OCR

### Start on Windows

Double-click `Start Notes App.cmd` in the project folder. Separate windows show
the backend and frontend logs; the frontend builds before it starts.
Keep the controller window open and press Enter in it to stop all the services
it started. If a service fails, its window stays open so you can see the error.
After the frontend build finishes, open `http://localhost:3000` in your browser.

Install uv, Node.js, the project dependencies (`uv sync` and `npm ci` in
`web`). Handwritten uploads are sent to Google Gemini for OCR. Configure
`OCR_MODEL` separately from `CHAT_MODEL` if you need a different OCR model.

The controller cannot clean up if it is forcibly closed; in that case, close
each remaining service window manually. If a port is already occupied, inspect
the relevant log window and stop the existing service before retrying.

Compare Gemini's transcription on a sample stored outside the repository, optionally with
a hand-typed reference. The output prefix must also be outside the repository;
the script refuses to overwrite existing output files.

```powershell
uv run python -m scripts.compare_ocr C:\private\sample.png C:\private\comparison --reference C:\private\reference.txt
```

Review the transcript and word error rate. OCR can misread or invent words.

