"""Extract page text before chunking a local lecture-notes PDF.
Keep original page numbers so later citations point to the actual PDF page.
Return skipped-page counts so scanned files cannot silently look successful.
"""

from pathlib import Path

from pypdf import PdfReader


# Page numbers or a short header alone are too little material for retrieval.
MIN_TEXT_CHARACTERS = 20


def load_pdf_pages(path: str | Path) -> tuple[list[dict], int]:
    pages = []
    skipped = 0
    with Path(path).open("rb") as source:
        reader = PdfReader(source)
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len("".join(text.split())) < MIN_TEXT_CHARACTERS:
                skipped += 1
                continue
            pages.append({"page": page_number, "text": text})
    return pages, skipped
