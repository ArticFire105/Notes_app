"""
Measure scoped retrieval without calling the chat model.
A local JSON file supplies questions and expected document pages.
One top-five search per question supplies hit@1, hit@3, and hit@5.
Misses identify questions that need closer manual inspection.

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
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.retrieve import resolve_scope, retrieve


def evaluate(questions: list[dict]) -> dict:
    if not questions:
        raise ValueError("Provide at least one evaluation question.")
    counts = {1: 0, 3: 0, 5: 0}
    misses = {1: [], 3: [], 5: []}
    for item in questions:
        subject_id, module_id = resolve_scope(item["subject"], item["module"])
        hits = retrieve(item["question"], subject_id, module_id, k=5)
        for k in counts:
            found = any(
                hit["document"] == item["expected_document"]
                and hit["page"] == item["expected_page"]
                for hit in hits[:k]
            )
            if found:
                counts[k] += 1
            else:
                misses[k].append(item)
    return {"counts": counts, "misses": misses, "total": len(questions)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure retrieval hit@1, hit@3, hit@5.")
    parser.add_argument("--questions", type=Path, default=Path("data/eval/questions.json"))
    args = parser.parse_args()
    try:
        questions = json.loads(args.questions.read_text(encoding="utf-8"))
        result = evaluate(questions)
    except Exception:
        print("FAIL evaluation: check the questions JSON, scope, model, and database setup.",
              file=sys.stderr)
        return 1
    for k, count in result["counts"].items():
        print(f"hit@{k}: {count}/{result['total']} = {count / result['total']:.1%}")
        for item in result["misses"][k]:
            print(f"  MISS: {item['question']} -> {item['expected_document']}"
                  f" · p.{item['expected_page']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

