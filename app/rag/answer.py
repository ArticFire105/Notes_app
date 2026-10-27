"""
Turn a scoped notes question into a grounded answer.
Retrieval runs before any Gemini model is created.
An empty result returns immediately to avoid spending credits.
The response keeps sources and token counts beside the answer.

This file serves both the CLI and authenticated API.
Phase 5 adds context limits and a request-only BYOK override.
Students can scope retrieval to a subject or a module.
Document IDs can further narrow the retrieval function.
Only official notes are eligible for these searches.
Embedding model identity keeps vector comparisons compatible.
The Phase 1 embedder remains responsible for query vectors.
The Phase 1 connection helper remains responsible for transactions.
Database values are passed separately from SQL text.
Module numbers are display labels rather than database IDs.
Original page numbers connect answers to the source notes.
Numbered context blocks give the model citation targets.
Source numbers follow the order supplied to the prompt.
An unsupported question must produce the not-found response.
Empty retrieval must not trigger a paid chat request.
Chat output is limited through the existing settings class.
Usage counts are returned for later accounting work.
The API router handles quota and cache before calling this function.
The same context limit applies to server-key and BYOK requests.
Real credentials belong only in the user's local configuration.
Secrets must never appear in printed exception diagnostics.
Offline tests replace settings and external service calls.
Tests must disable dotenv loading or replace Settings entirely.
Tests do not download weights or open live database connections.
Live source-page verification remains a manual check.
The evaluation example demonstrates the input format only.
Real evaluation questions stay outside version control.
Run the scripts from the repository root with uv.
"""

from app.config import Settings
from app.llm import get_chat_model, provider_errors
from app.rag.prompt import NOT_FOUND, SYSTEM_PROMPT, STRICT_PROMPT, build_context, source_label
from app.rag.retrieve import retrieve


def trim_context(hits, max_tokens):
    # Characters / 4 is an estimate, not the provider's exact tokenizer.
    max_chars = max_tokens * 4
    selected = []
    for hit in hits:
        candidate = [*selected, {**hit, "content": ""}]
        available = max_chars - len(build_context(candidate))
        if available <= 0:
            break
        candidate[-1]["content"] = hit["content"][:available]
        selected = candidate
        if len(hit["content"]) > available:
            break
    return selected, build_context(selected)


def answer_question(question, subject_id, module_id=None, document_id=None, *, api_key=None, mode="normal") -> dict:
    hits = retrieve(question, subject_id, module_id, document_id)
    if hits:
        hits, context = trim_context(hits, Settings().max_context_tokens)
    if not hits:
        return {
            "answer": NOT_FOUND, "sources": [],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    messages = [
        ("system", STRICT_PROMPT if mode == "strict" else SYSTEM_PROMPT),
        ("human", f"Notes context:\n{context}\n\nQuestion:\n{question}"),
    ]
    with provider_errors():
        model = get_chat_model() if api_key is None else get_chat_model(api_key)
        response = model.invoke(messages)
    # Some LangChain responses expose text blocks instead of a plain string.
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, (str, dict))
        )
    metadata = response.usage_metadata or {}
    return {
        "answer": content,
        "sources": [
            {"n": n, "document": hit["document"], "module": hit["module"],
             "page": hit["page"], "page_label": source_label(hit), "score": hit["score"]}
            for n, hit in enumerate(hits, start=1)
        ],
        "usage": {
            "input_tokens": metadata.get("input_tokens", 0),
            "output_tokens": metadata.get("output_tokens", 0),
        },
    }

