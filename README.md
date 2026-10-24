# Lecture Notes RAG

An open-source lecture-notes app for about 100 CSE students at Manipal Dubai.
The goal is answers grounded in department notes, with sources for each answer.
Phase 0 provides configuration and database setup; Phase 1 adds local PDF ingestion.

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
The interactive API documentation endpoints are disabled.

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
The helper keeps its token in memory and calls `/me` itself: it deliberately
does not print the token because repository rules forbid printing secrets.
Offline tests cover invalid tokens, domain lookalikes, student/rep upload
rejection, administrator upload attribution, and cache expiry.

Live OTP delivery, trigger execution, and RLS must be checked in your own
Supabase project; the offline suite mocks external services.
