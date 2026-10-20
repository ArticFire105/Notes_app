"""
Ask one scoped question from the command line.
Subject codes and module numbers are resolved to database IDs.
The answer pipeline supplies citations and usage counts.
Failures use fixed messages rather than raw library diagnostics.

This file belongs only to Phase 2 of the notes application.
The phase runs through scripts before an API is introduced.
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
No quota or cache behavior is introduced in this phase.
No authentication or frontend behavior is introduced here.
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

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.answer import answer_question
from app.rag.retrieve import resolve_scope


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask a question using official notes.")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--module", type=int)
    parser.add_argument("question")
    args = parser.parse_args()
    if not args.question.strip() or (args.module is not None and args.module < 1):
        parser.error("Provide a nonempty question and a positive module number.")
    try:
        subject_id, module_id = resolve_scope(args.subject, args.module)
        result = answer_question(args.question, subject_id, module_id)
    except Exception:
        # Driver and model errors may contain credentials; never echo them.
        print("FAIL question: check scope, settings, model access, and database setup.",
              file=sys.stderr)
        return 1
    print(result["answer"])
    print("\nSources:")
    for source in result["sources"]:
        module = "Whole subject" if source["module"] is None else f"Module {source['module']}"
        print(f"[{source['n']}] {source['document']} · {module} · p.{source['page']}"
              f" (score {source['score']:.3f})")
    usage = result["usage"]
    print(f"\nTokens: input={usage['input_tokens']}, output={usage['output_tokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

