"""
Transcribe private note pages with Gemini.
This module sits between file validation and chunking.
PDF pages are sent in small batches to limit requests.
Original page numbers are retained for citations.
Images are sent as one page.
The caller selects a request-only key or the server key.
The key is sent in a header, never in a URL.
The key and provider diagnostics are never logged.
The service receives the student's private document.
Users must be told about that transfer before upload.
Gemini is instructed not to guess illegible words.
Structured JSON keeps each page separate.
Every requested page must appear exactly once.
Suspicious repetitive output is rejected before indexing.
Validation cannot detect every convincing transcription error.
Students should review important material against originals.
Failed pages are reported alongside successful pages.
This keeps the previous searchable note intact.
The job reports affected page numbers without note text.
Transient rate limits receive bounded retries.
Exhausted quota becomes a safe actionable message.
No response text or raw exception is logged.
Documents are held in memory while processing.
The upload router enforces file and page limits.
PDF splitting reuses the project's pypdf dependency.
The HTTP client uses the existing httpx dependency.
The caller supplies progress callbacks for UI updates.
The endpoint is fixed to Google's public API.
The model name comes from backend settings.
The response is never used as an instruction.
Pages retain their original order.
No OCR output is silently repaired or embellished.
The caller handles storage and database transactions.
Tests mock HTTP and never need real credentials.
Run the offline suite with uv run pytest.
"""

import base64
from io import BytesIO
import json
import logging
import re
import time

import httpx
from pypdf import PdfReader, PdfWriter
from app.config import Settings

PAGES_PER_REQUEST = 5
logger = logging.getLogger(__name__)


class OCRFailure(ValueError):
    pass


def suspicious(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 25000:
        return True
    # Ordinary lists and tables repeat words; only detect uninterrupted loops.
    return bool(re.search(r"(.{1,40}?)\1{19,}", text.casefold()))


class OCRPages(list):
    def __init__(self):
        super().__init__()
        self.failed_pages = []


def read_batch(data, mime, numbers, model, key):
    request = {"contents": [{"parts": [
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}},
        {"text": "Transcribe handwriting exactly. Do not infer, correct, add headings, or complete unclear words; mark illegible text [unclear]. Return JSON object with pages array containing page and text. Use these original page numbers in order: " + ", ".join(map(str, numbers))},
    ]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 16384}}
    try:
        response = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, json=request, timeout=180.0)
        if response.status_code == 429:
            return None, "429/quota"
        if response.status_code >= 400:
            return None, f"HTTP {response.status_code}"
        result = response.json()
        candidates = result.get("candidates") or []
        if not candidates:
            return None, "safety block" if result.get("promptFeedback", {}).get("blockReason") else "empty response"
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
            return None, "safety block"
        if finish != "STOP":
            return None, "incomplete response"
        text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []))
        if not text.strip():
            return None, "empty response"
        found = json.loads(text)["pages"]
        if not isinstance(found, list) or any(not isinstance(item, dict) for item in found) or [item.get("page") for item in found] != numbers:
            return None, "parse error/page mismatch"
        if any(not isinstance(item.get("text"), str) or not item["text"].strip() for item in found):
            return None, "empty page"
        if any(suspicious(item["text"]) for item in found):
            return None, "repetition check or oversized page"
        return [{"page": item["page"], "text": item["text"].strip()} for item in found], None
    except httpx.TimeoutException:
        return None, "timeout"
    except (ValueError, KeyError, TypeError):
        return None, "parse error"
    except Exception:
        return None, "transport or provider error"


def request_batch(data, mime, numbers, model, key, attempts):
    reason = None
    for attempt in range(attempts):
        result, reason = read_batch(data, mime, numbers, model, key)
        if result is not None:
            return result, None
        logger.warning("OCR failed for pages %s: %s (attempt %s)", numbers, reason, attempt + 1)
        if attempt + 1 < attempts:
            time.sleep(2 ** (attempt + 1))
    return None, reason


def pdf_batches(data):
    reader = PdfReader(BytesIO(data))
    for start in range(0, len(reader.pages), PAGES_PER_REQUEST):
        writer = PdfWriter()
        end = min(start + PAGES_PER_REQUEST, len(reader.pages))
        for page in reader.pages[start:end]:
            writer.add_page(page)
        output = BytesIO()
        writer.write(output)
        yield list(range(start + 1, end + 1)), output.getvalue(), "application/pdf"


def transcribe(file_bytes, suffix, progress=None, api_key=None):
    settings = Settings()
    key = api_key or settings.google_api_key
    if hasattr(key, "get_secret_value"):
        key = key.get_secret_value()
    model = settings.ocr_model
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
        raise OCRFailure("OCR model setting is invalid.")
    batches = pdf_batches(file_bytes) if suffix == ".pdf" else [([1], file_bytes, "image/png" if suffix == ".png" else "image/jpeg")]
    pages = OCRPages()
    last_reason = None
    for numbers, data, mime in batches:
        found, last_reason = request_batch(data, mime, numbers, model, key, 3 if len(numbers) == 1 else 2)
        if found is not None:
            pages.extend(found)
        elif len(numbers) > 1:
            reader = PdfReader(BytesIO(data))
            for index, number in enumerate(numbers):
                writer = PdfWriter()
                writer.add_page(reader.pages[index])
                output = BytesIO()
                writer.write(output)
                found, last_reason = request_batch(output.getvalue(), mime, [number], model, key, 1)
                if found is None:
                    pages.failed_pages.append(number)
                else:
                    pages.extend(found)
        else:
            pages.failed_pages.extend(numbers)
        if progress:
            progress(numbers[-1])
    if not pages:
        prefix = "Google OCR quota is exhausted or busy on" if last_reason == "429/quota" else "Could not read"
        raise OCRFailure(prefix + " pages " + ", ".join(map(str, pages.failed_pages)) + ". Please try again later.")
    return pages
