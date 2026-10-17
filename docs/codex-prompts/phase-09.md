# Phase 9: Ask with an image (multimodal questions)

## Context
Phases 1–8 are done. Now a student can attach an image to a question (a photo of a diagram, a textbook problem, a past-paper question) and ask about it, still scoped to subject/module.
Flow: image + question → Gemini reads the image into a short text description → (question + description) is used as the retrieval query → final Gemini answer gets the image + retrieved chunks → answer with sources.
That is 2 Gemini calls, so it counts as 2 quota requests (say so in the UI).

## Task
1. `app/rag/answer.py`: `answer_with_image(question, image_bytes, scope..., api_key=None)`
   - reuse `prepare_image` from `app/ocr.py`,
   - step 1: `describe_image()`: "Describe/transcribe what this image shows in ≤ 80 words, focusing on technical terms" (low max tokens),
   - step 2: retrieve with `question + "\n" + description`,
   - step 3: answer with a multimodal message (system prompt from `prompt.py`, image block, numbered context, question).
   - Keep the same response shape as `answer_question` + `image_description` (so the UI can show what the model "saw").
2. `POST /ask` accepts an optional image: switch it to multipart, OR add `POST /ask/image`. Choose the simpler one and explain the choice. Max 5 MB, jpg/png/webp only. Quota: `try_consume` twice (or check there are ≥ 2 left first). Images are NOT stored by default; only processed in memory. Comment why (privacy, storage limit).
3. Cache: don't cache image questions (the key would need an image hash; skip for now and comment it).
4. UI: on the subject chat page, add an image uploader next to the chat input; show a thumbnail in the user's message and an expander "What the model saw in your image".
5. Tests: the size/type validation; the quota check needs 2 requests; mock Gemini.

Audio questions are NOT part of this phase.

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
