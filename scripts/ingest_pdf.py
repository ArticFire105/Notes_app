"""Run the Phase 1 ingestion pipeline for one local PDF from the command line.
Require an explicit subject, module, and title to keep stored scope intentional.
Report safe failures without printing library exceptions or backend credentials.
"""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.pipeline import IngestError, ingest_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest one PDF into pgvector.")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--module", type=int, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        document_id = ingest_pdf(
            args.pdf, args.subject, args.module, args.title, replace=args.replace
        )
    except IngestError as error:
        print(f"FAIL ingestion: {error}", file=sys.stderr)
        return 1
    except Exception:
        # Raw driver/model errors can include passwords, tokens, or URLs.
        print(
            "FAIL ingestion: check the PDF, settings, model access, and database setup. "
            "Database changes were rolled back if the transaction failed.",
            file=sys.stderr,
        )
        return 1
    print(f"PASS ingestion: document {document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
