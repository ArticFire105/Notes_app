"""
Transcribe private handwritten files using a local OCR model.
This module sits between personal upload and text chunking.
It is the only place that imports the OCR provider.
The provider can be replaced without changing the router.
Indra runs inference on the backend CPU.
It accepts scanned PDF and image files.
The first use may download local model weights.
No handwriting is sent to a cloud OCR service.
The uploaded file is held in a temporary directory.
The directory is removed when transcription ends.
The local model is loaded once per backend process.
Pages keep their original one-based page numbers.
The notes router checks file size before calling this module.
The router also checks file types and page limits.
OCR errors are returned without provider diagnostics.
Unreadable pages do not silently become valid notes.
The text is split before generating embeddings.
Only text reaches the embedding model.
A failed transcription leaves an existing note intact.
The caller handles authenticated storage paths.
The caller handles ownership and database transactions.
The caller never exposes the service role key.
This interface has no database dependency.
Tests can replace the local model with a fake.
Tests do not need real model downloads.
The OCR output should be checked against handwriting.
Handwriting and mathematical notation may be inaccurate.
PDF page count is constrained before this function runs.
Image size is constrained before this function runs.
Model loading is deferred until a note is uploaded.
Local OCR uses the CPU provider explicitly.
The model cache is managed by Indra OCR.
Only safe, generic errors reach API clients.
The caller never prints transcribed private notes.
Run the backend tests with uv run pytest.
"""

from functools import lru_cache
from html.parser import HTMLParser
from html import unescape
import re
from pathlib import Path
from tempfile import TemporaryDirectory


@lru_cache(maxsize=1)
def local_model():
    import indra_ocr
    return indra_ocr.load(threads=2, mode="ocr", providers=["CPUExecutionProvider"])


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"br", "p", "tr", "td", "th", "div", "li"}:
            self.parts.append("\n" if tag != "td" and tag != "th" else " ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        elif tag in {"p", "tr", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_ocr_text(text):
    parser = PlainText()
    parser.feed(unescape(text))
    text = "".join(parser.parts)
    text = re.sub(r"!\[[^]]*\]\([^)]*\)", "", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def transcribe(file_bytes: bytes, suffix: str, progress=None) -> list[dict]:
    with TemporaryDirectory(prefix="notes-ocr-") as folder:
        path = Path(folder) / ("upload" + suffix)
        path.write_bytes(file_bytes)
        pages = []
        for index, page in local_model().convert(path):
            if page.source == "error":
                raise ValueError("Could not read a page.")
            text = clean_ocr_text(page.text or page.markdown or "")
            if progress:
                progress(index + 1)
            if text:
                pages.append({"page": index + 1, "text": text})
        if not pages:
            raise ValueError("No readable handwriting found.")
        return pages
