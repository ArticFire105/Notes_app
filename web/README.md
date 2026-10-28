# Lecture Notes web app

The Phase 6 frontend uses Next.js App Router, TypeScript, Tailwind CSS, and
locally owned shadcn/ui Button, Input, and Card components. FastAPI remains
the only application API. The older `frontend/` Streamlit app is retained.

## Install and run

1. Install **Node.js 24 LTS** from [nodejs.org](https://nodejs.org/en/download)
   if needed. npm is included. Open a new PowerShell terminal and check:

   ```powershell
   node -v
   npm.cmd -v
   ```

   Node `v24.18.0` was already installed during development. Use `npm.cmd` on
   this Windows machine because PowerShell blocks the `npm.ps1` launcher.
   In Command Prompt, macOS, or Linux, `npm` works normally.

2. Install backend dependencies and run the Python tests from the repo root:

   ```powershell
   uv sync
   uv run pytest
   ```

3. Complete the existing backend setup from the root README: migrations,
   college email provider and SMTP, private `notes` Storage bucket, and model
   access. Include `{{ .Token }}` in Supabase's email template. The backend
   now accepts **6, 7, or 8 ASCII digits** for email codes. No new migration is
   needed. Make configuration changes yourself; never share credentials.

4. Start FastAPI from the repo root in terminal 1:

   ```powershell
   uv run uvicorn app.main:app --reload
   ```

5. Install and start Next.js in terminal 2:

   ```powershell
   cd web
   npm.cmd ci
   $env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000'
   npm.cmd run dev
   ```

6. Open **http://localhost:3000**. Use this hostname, rather than the frontend
   at `127.0.0.1:3000`, because backend CORS explicitly allows
   `http://localhost:3000`. Requests may include Authorization, Content-Type,
   and X-User-Api-Key headers. Cookies are not used for API authentication.

## Build and tests

Run these from `web/`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run start
```

Stop the dev server before starting the production server on the same port.
`npm test` uses Node's built-in runner with mocked fetch calls; it never
contacts real services. `npm run build` compiles TypeScript and all routes.
The first build downloads Inter and Playfair Display through `next/font`;
Next.js bundles the fonts and serves them locally to the browser.

`NEXT_PUBLIC_API_BASE_URL` is public configuration, never a credential.
It defaults to `http://127.0.0.1:8000`. Set it in the shell before starting
development or building production; Next.js embeds public variables at build
time, so changing a production API URL requires another build. Its placeholder
is documented in the root `.env.example`. No web dotenv file is required.
Never copy backend credentials into `web/`.

## Session behaviour

Access tokens, refresh tokens, saved BYOK keys, and per-subject chats stay in
memory. No localStorage, sessionStorage, cookies, or persistent browser cache
holds them. Refreshing, closing the tab, or logging out clears the session.
Navigation inside the app preserves it. Expiring tokens refresh through
FastAPI with a single shared refresh request. Failed authentication clears
the session. Old in-flight responses cannot restore a logged-out session.

Application data requests go through FastAPI. Login uses `/auth/send-code`,
`/auth/verify`, and `/auth/refresh`. Supabase and database clients stay on the
backend. Clicking View PDF obtains a signed URL from FastAPI and opens that
document in a new tab; external AI Studio and terms links are ordinary links.

## Test by hand

- Try a noncollege email. Then sign in with a real college address and a
  6–8 digit code matching your Supabase configuration. A failed resend must
  leave the code box visible for the last successfully emailed address.
- Confirm the five seeded subject cards show names, codes, and real module
  counts. Resize to a phone width and check the mobile navigation menu.
- Open a subject. Expand modules and view a ready PDF. Older documents
  ingested only through the CLI may lack Storage files; upload one using
  the admin screen if needed. Signed links expire and must be requested again.
- Ask with This module, This document, and Whole subject. Check source document,
  module, page, and relevance score. Switch subjects and check separate chats.
- Confirm remaining allowance updates. Repeating a cached answer should not
  spend another question. Exhaust the allowance using distinct supported
  questions and check the Settings link; global limits may also produce 429.
- In Settings, paste a key and click Save key, then Test key. Testing makes
  a small provider call. An edited draft is not used until saved. Navigate
  away and back; the saved key remains. Remove it and check that it clears.
  Refresh or log out and confirm both credentials and chat history clear.
- Promote your account to admin through the existing trusted SQL workflow.
  Log out and back in so `/me` reloads the role. Upload a PDF or PPTX up to 40 MB,
  watch status polling finish at ready or failed, and confirm the PDF appears
  under its module. Polling stops on completion or when leaving the page;
  the existing backend ingestion task continues independently.
- Sign in as a student: Admin upload must be hidden, and navigating directly
  to `/admin/upload` must show an access message. The backend also enforces
  admin permissions on every upload.
- Confirm My Notes, Past Papers, and Quiz show Coming soon.

Live OTP delivery, PDF access, ingestion, source accuracy, and provider calls
require your own running backend and remain manual integration checks.

## PDF and PowerPoint uploads

Both FastAPI and the admin form enforce a maximum of **40 MB**
(`40 * 1024 * 1024` bytes, inclusive). Larger files return HTTP 413 before
Storage or ingestion. Accepted formats are `.pdf` and `.pptx`. Old `.ppt`
files are rejected with instructions to save as `.pptx` in PowerPoint.

PowerPoint text boxes, grouped text, tables, and speaker notes are extracted
with `python-pptx`. Each slide uses its original one-based number in the same
`page` field used for PDFs. Empty slides are skipped without renumbering the
rest. Notes-only slides are included. These records then use the existing
chunking, embeddings, and transactional storage pipeline. Image-only slides
do not receive OCR in this change.

The backend derives file type from its generated Storage path, so no database
migration is required. Answer sources include `page_label`, displaying
**Slide N** for PowerPoint and **p.N** for PDFs. The generic
`/documents/{id}/file-url` endpoint signs either file type; the old `/pdf-url`
endpoint remains compatible. PowerPoint files download in their original
format rather than being converted for a browser preview.

After installing with `uv sync`, restart both servers. In Supabase Storage,
check that the private `notes` bucket and project upload limits allow at least
40 MB. If the bucket restricts MIME types, allow `application/pdf` and
`application/vnd.openxmlformats-officedocument.presentationml.presentation`.

Test a presentation with slide text, a blank middle slide, and a later slide
containing speaker notes. Wait for ready status, ask about the notes-only
content, and verify its original **Slide N** citation. Confirm PDFs still
show page citations, `.ppt` produces the conversion message, and files over
40 MB are rejected.

PPTX ingestion cleans soft line breaks (`\x0b`), other control characters,
and repeated whitespace before chunking. Blank slides, including empty
tables or blank speaker notes, are skipped without renumbering later slides.
A deck with no usable text shows **No readable text found in slides**.

Background failures save a short safe reason that the admin status card
displays. The FastAPI terminal logs the actual exception type and traceback
locations, including chained exceptions. Raw exception messages, source
lines, local variables, and full file paths are omitted because they can
contain credentials or authenticated URLs. The logged reason identifies
whether reading, chunking, embedding, or database storage failed.

After updating, restart FastAPI and Next.js and upload the original deck
again. Previously failed records are not automatically retried. Check a deck
with 23 slides and blanks between text slides, confirm its later slide
citations keep their original numbers, and try an entirely blank deck to
verify the readable error. No database migration or new setting is needed.

## Admin document deletion

On Admin upload, select a subject and use its **Documents** list. Delete asks
"Are you sure?" and names the document before making a request. Cancel leaves
it untouched. A successful deletion refreshes the list. The backend
`DELETE /documents/{id}` requires the current admin role; students and reps
receive 403, and a missing document returns 404.

The backend locks the module and document in the same order as ingestion.
It downloads a temporary in-memory copy of the original file, then deletes
the document's chunks (including embeddings), the subject's answer cache,
and the document row in one database transaction. It removes the source file
through the private `notes` Storage API before committing. SQL failures roll
back all database changes. A handled Storage or commit failure attempts to
restore the original file at the same path before returning a safe 503 error.
Failures and restoration errors are logged without raw credential-bearing
diagnostics. Documents with no Storage path can still be removed.

Storage and Postgres do not share a transaction. This implementation handles
ordinary failures with rollback and compensation; it cannot guarantee
all-or-nothing deletion if the process dies between external removal and SQL
commit, if the commit outcome is unknown, or if Storage also rejects restoration.
A restoration failure is explicitly reported and requires an administrator
to inspect the document and re-upload the original if needed. A durable
deletion/recovery queue would be required for crash recovery; it is not
implemented here. Storage must be managed through its API, as explained in
[Supabase's Storage schema documentation](https://supabase.com/docs/guides/storage/schema/design).

No migration, new setting, or new dependency is needed. Restart both servers
after updating. Test using a disposable PDF or PPTX:

1. Upload it and ask a supported question to populate the subject cache.
2. Click Delete and cancel; confirm the document remains.
3. Delete and confirm; verify the refreshed list omits it and its file is
   absent from the private `notes` bucket.
4. In Supabase SQL Editor, check that its `documents` row and `chunks` rows
   are gone and the subject's `answer_cache` rows are cleared. Existing chat
   messages are historical session data; new questions use the updated scope.
5. Log in as a student: Admin upload stays hidden, and an authenticated
   DELETE request must return 403. A repeat admin DELETE for the removed ID
   must return 404.

The backend tests use real local SQLite transactions with fake Storage to
verify deletion and rollback, and mock Supabase authentication. PostgreSQL
locking and live Supabase behaviour still require the manual checks above.

## Text-only embedding inputs

Document and query embedding entry points reject dictionaries, message
objects, path objects, and other non-string values before calling the model.
Media filenames/URLs, YouTube links, and `file://` references are replaced
with the literal text `[media reference]`. Empty chunks are removed before
embedding and database insertion, keeping chunk/vector alignment intact.

Sentence Transformers media routing is disabled on the cached model. Its
existing text prompt formatting, Document/SearchQuery prompts, normalization,
and 768-dimensional vectors are retained for ordinary PDF text. No video
decoding dependency is added or required. Original source files are unchanged.

If a batch fails, the backend tests its chunks individually to identify a
reproducible failure. Logs show the original zero-based chunk index and at
most 80 characters of a conservatively redacted preview. Credential-like
content and URLs are masked before truncation. Batch-only failures are
labelled as such rather than assigning an incorrect chunk index. The admin
failure reason includes the exception type and identifies video preprocessing
if it appears in the actual traceback, instead of suggesting model access
for every failure.

Restart FastAPI to replace the cached embedder, then re-upload the failed
PPTX. Test a deck containing `demo.mp4`, a YouTube link, and normal lecture
text. Wait for ready status and verify Slide N citations. Upload a normal
PDF as a regression check. Existing failed uploads do not retry themselves.
No new dependency, setting, or migration is needed. Offline tests cover the
real wrapper/input formatter using a fake encoder; live model inference must
be checked with your own backend.

The shared controls follow the official
[shadcn/ui setup](https://ui.shadcn.com/docs/installation/next) and can be edited
directly in `components/ui/`. `components.json` retains the component aliases.
