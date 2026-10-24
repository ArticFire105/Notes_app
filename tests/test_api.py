"""
Test the Phase 3 HTTP flow with in-memory doubles.
Lifespan model loading is replaced before TestClient starts.
Database, Storage, and Gemini constructors fail if reached.
Uploaded PDFs are generated locally rather than using real notes.

This module belongs to Phase 3 of the notes application.
The API wraps the existing ingestion and answering code.
It runs locally until authentication is added in Phase 4.
Do not deploy before Phase 4.

Database credentials stay on the backend.
The Storage service role key stays on the backend.
Responses never include configuration objects.
Raw provider errors must not reach clients or logs.

Subjects and modules define the official-notes scope.
Database IDs are distinct from module display numbers.
Uploaded PDFs live in a private notes bucket.
Signed URLs grant temporary access to one stored PDF.

Uploads are checked before background ingestion.
Document status supports polling during ingestion.
Chunks and readiness are committed together.
Background tasks are in-process rather than a durable queue.

Startup reuses the cached Phase 1 embedding model.
Question answers reuse the Phase 2 answer function.
Tests replace model loading and all external calls.
Tests never need real credentials or a real dotenv file.

No authentication, quota, cache, or frontend is added here.
Run the API from the repository root.
Use uv run pytest for the offline test suite.
"""

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pypdf import PdfWriter
import pytest

from app import config, db, embeddings, llm, main, storage
from app.auth import get_current_user
from app.routers import ask, documents, subjects

DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must replace settings and external services.")

    # Fail immediately if a test accidentally reaches dotenv or a real client.
    monkeypatch.setattr(config.Settings, "__init__", forbidden)
    monkeypatch.setattr(db.psycopg, "connect", forbidden)
    monkeypatch.setattr(embeddings, "HuggingFaceEmbeddings", forbidden)
    monkeypatch.setattr(llm, "init_chat_model", forbidden)
    monkeypatch.setattr(storage, "create_client", forbidden)


@pytest.fixture
def record():
    return {
        "id": DOCUMENT_ID, "title": "Memory", "module": 2,
        "page_count": None, "status": "processing",
        "created_at": datetime(2026, 10, 21, tzinfo=timezone.utc), "error": None,
    }


@pytest.fixture
def backend(monkeypatch):
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    for router in (ask, documents, subjects):
        monkeypatch.setattr(router, "get_conn", context)
    startup = MagicMock()
    monkeypatch.setattr(main, "get_embedder", startup)
    generate = MagicMock(return_value={
        "answer": "Pages [1]",
        "sources": [{"n": 1, "document": "Memory", "module": 2, "page": 14, "score": 0.9}],
        "usage": {"input_tokens": 20, "output_tokens": 5},
    })
    monkeypatch.setattr(ask, "answer_question", generate)
    upload = MagicMock()
    ingest = MagicMock()
    remove = MagicMock()
    sign = MagicMock(return_value="https://example.invalid/temporary")
    monkeypatch.setattr(documents, "upload_pdf", upload)
    monkeypatch.setattr(documents, "ingest_pdf", ingest)
    monkeypatch.setattr(documents, "delete_pdf", remove)
    monkeypatch.setattr(documents, "signed_url", sign)
    monkeypatch.setattr(documents, "uuid4", lambda: DOCUMENT_ID)
    return SimpleNamespace(cursor=cursor, startup=startup, generate=generate,
                           upload=upload, ingest=ingest, remove=remove, sign=sign)


@pytest.fixture
def client(backend):
    main.app.dependency_overrides[get_current_user] = lambda: {
        "id": DOCUMENT_ID, "email": "admin@dxb.manipal.edu", "role": "admin",
    }
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture
def pdf():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    return output.getvalue()


def post_pdf(client, pdf, **data):
    return client.post(
        "/documents", files={"file": ("memory.pdf", pdf, "application/pdf")},
        data={"subject_id": "1", "module_id": "12", "title": "Memory", **data},
    )


def test_health_and_startup_once(client, backend):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health").status_code == 200
    backend.startup.assert_called_once()


@pytest.mark.parametrize("question", ["", " ", "x" * 1001])
def test_invalid_question_never_calls_services(client, backend, question):
    response = client.post("/ask", json={"question": question, "subject_id": 1})
    assert response.status_code == 422
    backend.generate.assert_not_called()
    backend.cursor.execute.assert_not_called()


def test_ask_uses_validated_scope(client, backend):
    backend.cursor.fetchone.side_effect = [(1,), (12,), (12,)]
    response = client.post("/ask", json={
        "question": " paging? ", "subject_id": 1, "module_id": 12,
        "document_id": str(DOCUMENT_ID),
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "Pages [1]"
    backend.generate.assert_called_once_with("paging?", 1, 12, DOCUMENT_ID)


@pytest.mark.parametrize("rows,payload", [
    ([None], {"subject_id": 99}),
    ([(1,), None], {"subject_id": 1, "module_id": 99}),
    ([(1,), (12,), (13,)], {"subject_id": 1, "module_id": 12, "document_id": str(DOCUMENT_ID)}),
])
def test_ask_unknown_scope_is_404(client, backend, rows, payload):
    backend.cursor.fetchone.side_effect = rows
    assert client.post("/ask", json={"question": "paging", **payload}).status_code == 404
    backend.generate.assert_not_called()


def test_subject_and_module_lists(client, backend):
    backend.cursor.fetchall.return_value = [{"id": 1, "code": "OS", "name": "Operating Systems"}]
    assert client.get("/subjects").json()[0]["code"] == "OS"
    backend.cursor.fetchone.return_value = {"id": 1}
    backend.cursor.fetchall.return_value = [
        {"id": 12, "subject_id": 1, "number": 2, "title": "Memory"}
    ]
    assert client.get("/subjects/1/modules").json()[0]["id"] == 12


@pytest.mark.parametrize("url", ["/subjects/99/modules", "/modules/99/documents",
                                f"/documents/{DOCUMENT_ID}", f"/documents/{DOCUMENT_ID}/pdf-url"])
def test_unknown_resources(client, backend, url):
    backend.cursor.fetchone.return_value = None
    assert client.get(url).status_code == 404


def test_document_list_polling_and_signed_url(client, backend, record):
    backend.cursor.fetchone.return_value = {"id": 12}
    backend.cursor.fetchall.return_value = [record]
    assert client.get("/modules/12/documents").json()[0]["module"] == 2
    backend.cursor.fetchone.return_value = {
        **record, "status": "ready", "page_count": 1, "storage_path": "official/OS/example.pdf",
    }
    response = client.get(f"/documents/{DOCUMENT_ID}")
    assert response.json()["status"] == "ready"
    assert "storage_path" not in response.json()
    assert client.get(f"/documents/{DOCUMENT_ID}/pdf-url").json() == {
        "url": "https://example.invalid/temporary"
    }
    backend.sign.assert_called_once_with("official/OS/example.pdf")


def test_cli_document_without_storage_has_no_url(client, backend, record):
    backend.cursor.fetchone.return_value = {**record, "storage_path": None}
    assert client.get(f"/documents/{DOCUMENT_ID}/pdf-url").status_code == 404
    backend.sign.assert_not_called()


def test_upload_returns_processing_and_schedules_ingest(client, backend, record, pdf):
    backend.cursor.fetchone.side_effect = [{"code": "OS"}, {"number": 2}, record]
    response = post_pdf(client, pdf)
    assert response.status_code == 202
    assert response.json()["id"] == str(DOCUMENT_ID)
    assert response.json()["status"] == "processing"
    backend.upload.assert_called_once_with(
        pdf, f"official/OS/module-2/{DOCUMENT_ID}.pdf"
    )
    insert = next(call for call in backend.cursor.execute.call_args_list
                  if "insert into documents" in call.args[0])
    assert "uploaded_by" in insert.args[0]
    assert insert.args[1][-1] == DOCUMENT_ID
    backend.ingest.assert_called_once_with(
        pdf, "OS", 2, "Memory", document_id=DOCUMENT_ID
    )


def test_ingest_is_queued_not_run_by_upload_handler(backend, record, pdf):
    backend.cursor.fetchone.side_effect = [{"code": "OS"}, {"number": 2}, record]
    tasks = BackgroundTasks()
    documents.queue_document(tasks, pdf, 1, 12, "Memory", DOCUMENT_ID)
    backend.ingest.assert_not_called()
    assert len(tasks.tasks) == 1


@pytest.mark.parametrize("filename,content_type,content", [
    ("notes.txt", "text/plain", b"text"),
    ("notes.pdf", "application/pdf", b"not a pdf"),
    ("notes.pdf", "application/pdf", b"%PDF-1.7 broken"),
])
def test_bad_file_returns_400_without_upload(client, backend, filename, content_type, content):
    response = client.post(
        "/documents", files={"file": (filename, content, content_type)},
        data={"subject_id": 1, "module_id": 12, "title": "Memory"},
    )
    assert response.status_code == 400
    backend.upload.assert_not_called()


def test_size_limit_and_blank_title(client, backend, pdf, monkeypatch):
    monkeypatch.setattr(documents, "MAX_PDF_BYTES", len(pdf))
    assert post_pdf(client, pdf).status_code == 400
    assert post_pdf(client, pdf, title=" ").status_code == 400
    backend.upload.assert_not_called()


@pytest.mark.parametrize("rows", [[None], [{"code": "OS"}, None]])
def test_upload_requires_subject_module_relationship(client, backend, pdf, rows):
    backend.cursor.fetchone.side_effect = rows
    assert post_pdf(client, pdf).status_code == 404
    backend.upload.assert_not_called()


def test_failed_sql_insert_cleans_storage(client, backend, pdf):
    backend.cursor.fetchone.side_effect = [
        {"code": "OS"}, {"number": 2}, RuntimeError("dummy-secret"),
    ]
    response = post_pdf(client, pdf)
    assert response.status_code == 500
    assert "dummy-secret" not in response.text
    backend.remove.assert_called_once_with(f"official/OS/module-2/{DOCUMENT_ID}.pdf")
    backend.ingest.assert_not_called()


def test_background_failure_is_recorded_safely(backend):
    backend.ingest.side_effect = RuntimeError("dummy-secret")
    documents.finish_upload(b"pdf", DOCUMENT_ID, "OS", 2, "Memory")
    sql, params = backend.cursor.execute.call_args.args
    assert "status = 'failed'" in sql
    assert params[1] == DOCUMENT_ID
    assert "dummy-secret" not in params[0]


def test_background_database_failure_does_not_escape(backend):
    backend.ingest.side_effect = RuntimeError("dummy-secret")
    backend.cursor.execute.side_effect = RuntimeError("dummy-db-secret")
    documents.finish_upload(b"pdf", DOCUMENT_ID, "OS", 2, "Memory")


def test_internal_errors_never_return_or_log_details(client, backend, caplog):
    backend.cursor.execute.side_effect = RuntimeError("dummy-db-secret")
    response = client.get("/subjects")
    assert response.status_code == 500
    assert "dummy-db-secret" not in response.text + caplog.text


def test_storage_helpers_use_private_bucket_and_backend_key(monkeypatch):
    settings = SimpleNamespace(
        supabase_url="https://example.invalid", supabase_service_role_key=SecretStr("dummy-role")
    )
    constructor = MagicMock()
    bucket = constructor.return_value.storage.from_.return_value
    bucket.create_signed_url.return_value = {"signedURL": "https://example.invalid/signed"}
    monkeypatch.setattr(storage, "Settings", lambda: settings)
    monkeypatch.setattr(storage, "create_client", constructor)
    storage.upload_pdf(b"pdf", "official/OS/module-2/test.pdf")
    assert storage.signed_url("official/OS/module-2/test.pdf") == "https://example.invalid/signed"
    storage.delete_pdf("official/OS/module-2/test.pdf")
    constructor.assert_called_with("https://example.invalid", "dummy-role")
    constructor.return_value.storage.from_.assert_called_with("notes")
    bucket.upload.assert_called_once_with(
        "official/OS/module-2/test.pdf", b"pdf", file_options={"content-type": "application/pdf"}
    )
    bucket.create_signed_url.assert_called_once_with("official/OS/module-2/test.pdf", 3600)
    bucket.remove.assert_called_once_with(["official/OS/module-2/test.pdf"])

