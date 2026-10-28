"""
Compare Gemini OCR with a student's reference transcript.
This script runs outside the upload and indexing flow.
It reads only the input paths supplied by the student.
It never adds samples or results to the repository.
Use a private, local folder for the sample files.
The image or PDF is sent to Google Gemini for OCR.
The backend preserves original page numbers.
The results are written next to the chosen output prefix.
Use output paths outside version control.
An optional reference text enables word error rates.
Reference text should contain the words in reading order.
Word error rate counts insertions, deletions, and substitutions.
Lower error rate means closer agreement with the reference.
The score does not measure semantic correctness.
Review important errors manually as well.
No model weights are included in this repository.
Gemini may make transcription errors.
OCR results can contain private student information.
Do not upload results to a public repository.
The configured server API key is used for transcription.
Configuration follows the backend settings.
The backend uses the same transcription function.
This ensures the comparison uses the actual app flow.
PDF rendering uses one-based page numbers.
Existing output files are not overwritten.
The optional reference is never modified.
Use a representative selection of handwritten pages.
Accuracy and speed depend on hardware and handwriting.
Run backend checks with uv run pytest.
"""

import argparse
import re
from pathlib import Path

from app.ocr import transcribe


def word_error_rate(reference, actual):
    expected = re.findall(r"\w+", reference.casefold())
    words = re.findall(r"\w+", actual.casefold())
    if not expected:
        raise ValueError("Reference contains no words.")
    previous = list(range(len(words) + 1))
    for i, word in enumerate(expected, 1):
        current = [i]
        for j, found in enumerate(words, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != found)))
        previous = current
    return previous[-1] / len(expected)


def main():
    parser = argparse.ArgumentParser(description="Compare Gemini OCR with a reference transcript.")
    parser.add_argument("sample", type=Path)
    parser.add_argument("output_prefix", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    data = args.sample.read_bytes()
    reference = args.reference.read_text(encoding="utf-8") if args.reference else None
    pages = transcribe(data, args.sample.suffix.lower())
    result = "\n\n".join(page["text"] for page in pages)
    output = args.output_prefix.with_name(args.output_prefix.name + "-gemini.txt")
    with output.open("x", encoding="utf-8") as file:
        file.write(result)
    print(f"Gemini: saved {len(pages)} pages to {output}")
    if reference is not None:
        print(f"Gemini word error rate: {word_error_rate(reference, result):.1%}")


if __name__ == "__main__":
    main()
