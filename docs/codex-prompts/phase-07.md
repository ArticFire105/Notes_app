# Phase 7: Handwritten notes section (Gemini vision OCR → same RAG)

## Context
Phases 1–6 are done. Now students can ADD their own handwritten notes as photos. They stay separate from official notes.
Flow: photo(s) → Storage (private) → Gemini vision transcribes each page to text → student reviews/edits the text → chunk + embed → `chunks` with `source_type='student'` and `owner_id = the student`.
Default privacy: a student's notes are visible ONLY to that student. Sharing comes later.
Add the library `pillow`.

## Task
1. `supabase/migrations/0005_student_notes.sql`: add `owner_id uuid references profiles(id)` and `is_shared boolean default false` to `documents` and `chunks` (if not there). Add `source_kind text` to documents (`pdf` | `images`). Index `chunks(owner_id)`. RLS: students can read their own student documents.
2. `app/ocr.py`:
   - `prepare_image(bytes) -> bytes`: open with Pillow, fix EXIF rotation, resize so the longest side is ≤ 1600 px, and convert to JPEG. Comment why (fewer tokens, faster, cheaper).
   - `transcribe_page(image_bytes, api_key=None) -> str`: one Gemini multimodal call via the LangChain chat model (image as a base64 content block). Prompt: "Transcribe this handwritten page to Markdown exactly. Keep headings, lists, formulas (use LaTeX), diagrams as [diagram: short description]. Mark unreadable words as [?]". Return the text.
   - This module will also be reused in Phase 8 for scanned past papers. Keep it generic.
3. Endpoints (student or admin, logged in):
   - `POST /notes/transcribe` (multipart: up to 10 images, subject_id, module_id optional): checks type/size → `prepare_image` → upload to `student/{user_id}/{uuid}/page-N.jpg` → transcribe → return the text per page (NOT saved to chunks yet). Each image counts as 1 request in quota (or uses BYOK).
   - `POST /notes` (subject_id, module_id, title, pages: list of edited text, storage paths): creates a `documents` row (`source_type='student'`, `owner_id`) → chunk + embed → chunks. Reuse the Phase 1 pipeline with a "pages of text" entry point instead of a PDF.
   - `GET /notes/mine`, `DELETE /notes/{id}` (only the owner; delete the chunks + storage files).
4. Retrieval change in `app/rag/retrieve.py`: new param `include_my_notes: bool` + `user_id`. SQL becomes
   `AND (source_type = 'official' OR (source_type = 'student' AND owner_id = %s))` when on. Default off. Sources show a "📝 your notes" label.
5. UI `frontend/pages/my_notes.py`: upload photos → show each transcription in an editable text area next to the image → "Save to my notes" → list of my notes with delete. On the subject chat page: a toggle "Include my handwritten notes".
6. Tests: the SQL builder produces the right WHERE for both toggle states; `prepare_image` shrinks a big image.

Never let one student's notes appear in another student's answers. Write a test for that rule.

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
