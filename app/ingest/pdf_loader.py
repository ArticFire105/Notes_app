"""Extract page text before chunking a local lecture-notes PDF.
Keep original page numbers so later citations point to the actual PDF page.
Return skipped-page counts so scanned files cannot silently look successful.
"""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


# Page numbers or a short header alone are too little material for retrieval.
MIN_TEXT_CHARACTERS = 20


def load_pdf_pages(path: str | Path | bytes) -> tuple[list[dict], int]:
    pages = []
    skipped = 0
    # Share page extraction between CLI paths and uploaded PDF bytes.
    source = BytesIO(path) if isinstance(path, bytes) else Path(path).open("rb")
    with source:
        reader = PdfReader(source)
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len("".join(text.split())) < MIN_TEXT_CHARACTERS:
                skipped += 1
                continue
            pages.append({"page": page_number, "text": text})
    return pages, skipped
