# Phase 8: Previous-year papers + Quiz (practice + "likely" questions)

## Context
Phases 1–7 are done. Admin (me) uploads previous-year question papers per subject with the exam year.
Then a Quiz section uses them in 2 ways:
- **Practice:** real past questions for a module, plus a few NEW practice questions generated from the official notes.
- **Likely questions:** find topics asked again and again across years → rank them → show the evidence ("asked in 2023, 2024, 2025").
  This is a pattern guess, NOT a prediction guarantee. The UI must say so.

## Task
1. `supabase/migrations/0006_quiz.sql` (see plan schema): `past_paper_questions` (document_id, subject_id, module_id null, exam_year, q_number, text, marks, embedding vector(768), group_id null), `quizzes` (user_id, subject_id, module_id, kind, created_at), `quiz_items` (quiz_id, kind 'past'|'practice'|'likely', question, model_answer, sources jsonb, past_question_ids int[]). RLS: users read only their own quizzes.
2. Upload: `POST /papers` (admin; PDF, subject_id, exam_year, title) → Storage `past_papers/...` → `documents` row with `source_type='past_paper'` → text per page via pypdf; if a page has no text, use `app/ocr.py` from Phase 7 (scanned papers) → also chunk + embed into `chunks` (so past papers are searchable when the user wants) → extract questions.
3. `app/quiz/extract.py`: Gemini with structured output (`with_structured_output` + Pydantic `PastQuestion{q_number, text, marks, module_guess}` list) per page batch. `module_guess` comes from giving the model the module titles of that subject. Save as `status='needs_review'`.
   `GET /papers/{id}/questions` + `PUT /papers/{id}/questions` so I can fix the extracted questions and modules before they're used.
4. `app/quiz/likely.py` (no LLM needed for the grouping, so it's cheap and explainable):
   - embed each question (document prompt),
   - greedy grouping: a question joins the first group whose centroid has cosine ≥ `SIMILARITY_THRESHOLD` (constant, start 0.80), else it starts a new group,
   - score = number of DISTINCT exam years in the group (then total marks as the tie-break),
   - store `group_id`. `GET /quiz/likely?subject_id&module_id` returns the top groups with their member questions + years.
   - Then ONE Gemini call rewrites each top group into a clean "likely question" (counts as 1 quota request).
5. `app/quiz/generate.py`: `POST /quiz` (subject_id, module_id, n_past=3, n_practice=2) → picks random reviewed past questions for that module + generates `n_practice` new questions grounded in retrieved official chunks (cite sources) → saves the quiz. `POST /quiz/items/{id}/answer` → generates a model answer from the notes with sources (1 quota request, cached via the Phase 5 cache).
6. UI `frontend/pages/past_papers.py` (list per subject/year, view PDF, admin upload + question review table) and `frontend/pages/quiz.py` (tabs: Practice | Likely questions; each question has "Show model answer" with sources; a disclaimer on the Likely tab).
7. Tests: grouping on a tiny fake set of vectors (2 similar + 1 different → 2 groups); scoring counts distinct years, not total questions.

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
