# Phase 2: Retrieval with SQL WHERE filter + Gemini answer with sources

## Context
Phase 1 is done: `scripts/ingest_pdf.py` stores chunks with `subject_id`, `module_id`, `source_type`, `page`, `embedding` in pgvector.
Now: ask a question scoped to a module or a whole subject, retrieve with pgvector + SQL filter, and answer with Gemini citing sources. Script only, no API.

## Task
1. `app/rag/retrieve.py`: `retrieve(question, subject_id, module_id=None, document_id=None, k=5) -> list[dict]`
   - Embed the question with `embed_query` (the query prompt, not the document prompt).
   - ONE readable SQL query using cosine distance `<=>`:
     `WHERE subject_id = %s AND source_type = 'official' AND embedding_model = %s`, plus `AND module_id = %s` / `AND document_id = %s` only when given (build the SQL with simple, safe parameter lists, never string-format user input).
     JOIN `documents` and `modules` so each hit has: content, page, document title, module number/title, and `score = 1 - distance`.
   - Before the query, run `SET LOCAL hnsw.iterative_scan = relaxed_order` inside the transaction if pgvector >= 0.8 (see the plan's HNSW note), so filtered searches still return k rows. Comment why.
2. `app/llm.py`: `get_chat_model(api_key=None)` using LangChain `init_chat_model(settings.CHAT_MODEL, ...)` with `temperature=0.2` and a max output tokens setting from config (`MAX_OUTPUT_TOKENS`, default 800; add it to `.env.example`). `api_key` param exists now for BYOK later; default uses the server key.
3. `app/rag/prompt.py`: the system prompt as a constant. Rules for the model: answer ONLY from the given context; if the context doesn't contain it, say "Not found in your notes for this scope"; cite like `[1]`, `[2]` matching numbered context blocks; short, exam-friendly answers.
   `build_context(hits)` numbers each chunk: `[1] (OS · Module 2 · Memory.pdf · p.14) <text>`.
4. `app/rag/answer.py`: `answer_question(question, subject_id, module_id=None, document_id=None) -> dict` with keys `answer`, `sources` (list of {n, document, module, page, score}), `usage` (input/output tokens from the response's `usage_metadata`). If retrieval returns 0 hits, return the "not found" answer WITHOUT calling Gemini (saves credits).
5. `scripts/ask.py`: CLI `--subject OS [--module 2] "question"`. Print the answer, then the sources as a list, then token usage.
6. `scripts/eval_retrieval.py` + `data/eval/questions.example.json` (commit the example, gitignore the real file): each item is `{question, subject, module, expected_document, expected_page}`. The script prints hit@k (did the expected page appear in the top k?) for k=1,3,5, plus the misses. No Gemini calls in this script.
7. `tests/test_prompt.py`: test that `build_context` numbers sources correctly (no DB/LLM).

Keep the retrieval SQL visible in one place. I want to read and understand it.

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
