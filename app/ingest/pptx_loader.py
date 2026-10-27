"""
Extract text and speaker notes before lecture-note chunking.
Each PowerPoint slide keeps its one-based source number.
This loader plugs into the same pipeline as PDF extraction.
The return shape remains a list of page and text dictionaries.
Original slide order controls citation numbering.
Skipped slides never renumber later slides.
Blank slides contribute to the total slide count.
Short but meaningful slide titles are preserved.
Speaker notes belong to the slide that owns them.
Notes are labelled separately from visible slide text.
Notes placeholders avoid duplicating page headers and footers.
No missing notes slide is created during reading.
Text boxes and text placeholders are included.
Text in grouped shapes is included recursively.
Table cells are included in row order.
Images are not transcribed in this phase.
Diagrams are not sent to an OCR service.
Animation and layout are not reproduced.
PowerPoint is not launched during parsing.
Uploaded bytes are read through an in-memory stream.
Local paths support the same extraction helper.
Streams close after extraction completes.
Parsing errors propagate to the safe upload boundary.
Empty presentations are rejected by the upload boundary.
Old binary PowerPoint files require conversion.
The loader does not contact a remote service.
The loader does not read application configuration.
The loader does not open a database connection.
The loader does not create embeddings itself.
Chunking preserves these slide boundaries.
Embedding and storage remain in the shared ingestion pipeline.
Tests create small presentations with fake lecture text.
Run uv run pytest from the repository root.
"""

from io import BytesIO
from pathlib import Path
import re
import unicodedata

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


NO_READABLE_SLIDES = "No readable text found in slides"


class NoReadableSlidesError(ValueError):
    """The presentation contains no usable slide text or speaker notes."""


def clean_slide_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # PowerPoint soft breaks are vertical tabs; PostgreSQL rejects NUL characters.
    text = "".join(
        "\n" if character in "\n\v\f" else
        " " if unicodedata.category(character) in {"Cc", "Cf", "Cs"} else character
        for character in text
    )
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def shape_text(shapes) -> list[str]:
    texts = []
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            texts.extend(shape_text(shape.shapes))
        elif shape.has_text_frame:
            texts.append(shape.text_frame.text)
        elif shape.has_table:
            for row in shape.table.rows:
                cells = [clean_slide_text(cell.text) for cell in row.cells]
                if any(cells):
                    texts.append(" | ".join(cells))
    return texts


def load_pptx_pages(path: str | Path | bytes) -> tuple[list[dict], int]:
    source = BytesIO(path) if isinstance(path, bytes) else Path(path).open("rb")
    pages = []
    skipped = 0
    with source:
        presentation = Presentation(source)
        for number, slide in enumerate(presentation.slides, start=1):
            parts = [clean_slide_text(part) for part in shape_text(slide.shapes)]
            text = "\n".join(part for part in parts if part)
            # Accessing notes_slide creates one if absent; check first to keep parsing read-only.
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame
                notes_text = clean_slide_text(notes.text) if notes is not None else ""
                if notes_text:
                    text = "\n\n".join(filter(None, [text, "Speaker notes:\n" + notes_text]))
            if text:
                pages.append({"page": number, "text": text})
            else:
                skipped += 1
    if not pages:
        raise NoReadableSlidesError(NO_READABLE_SLIDES)
    return pages, skipped
