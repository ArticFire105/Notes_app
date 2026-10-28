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
from contextlib import contextmanager
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock
from uuid import UUID

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pypdf import PdfWriter
from pptx import Presentation
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
    monkeypatch.setattr(ask, "has_note", lambda *args: False)
    monkeypatch.setattr(ask.cache, "scope_version", lambda subject_id: "documents-v1")
    monkeypatch.setattr(ask.cache, "get", lambda key: None)
    monkeypatch.setattr(ask.cache, "put", MagicMock())
    monkeypatch.setattr(ask.quota, "dubai_day", lambda: "2026-10-24")
    monkeypatch.setattr(ask.quota, "try_consume", lambda *args: True)
    monkeypatch.setattr(ask.quota, "remaining", lambda user_id: 4)
    monkeypatch.setattr(ask.quota, "record_usage", MagicMock())
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
    monkeypatch.setattr(documents, "upload_document", upload)
    monkeypatch.setattr(documents, "ingest_document", ingest)
    monkeypatch.setattr(documents, "delete_document", remove)
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


@pytest.mark.parametrize("environment", [None, "production", "staging", "invalid"])
def test_docs_disabled_outside_development(monkeypatch, backend, environment):
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    with TestClient(main.create_app()) as local_client:
        for path in ("/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"):
            assert local_client.get(path).status_code == 404
        assert local_client.get("/health").status_code == 200


def test_development_docs_have_authorize_and_keep_routes_protected(monkeypatch, backend):
    monkeypatch.setenv("APP_ENV", "development")
    with TestClient(main.create_app()) as local_client:
        response = local_client.get("/docs")
        assert response.status_code == 200
        assert "/openapi.json" in response.text
        assert '"persistAuthorization": false' in response.text
        schema = local_client.get("/openapi.json").json()
        assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
            "type": "http", "scheme": "bearer",
        }
        assert schema["paths"]["/me"]["get"]["security"] == [{"HTTPBearer": []}]
        assert local_client.get("/me").status_code == 401
        assert local_client.get("/redoc").status_code == 404


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
    backend.generate.assert_called_once_with("paging?", 1, 12, DOCUMENT_ID, mode="normal")


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


def test_upload_returns_processing_and_schedules_ingest(client, backend, record, pdf, monkeypatch):
    enqueue = MagicMock()
    monkeypatch.setattr(documents, "enqueue_document", enqueue)
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
    assert enqueue.call_args.args[1] == (pdf, DOCUMENT_ID, "OS", 2, "Memory", "pdf")


def test_ingest_is_queued_not_run_by_upload_handler(backend, record, pdf, monkeypatch):
    backend.cursor.fetchone.side_effect = [{"code": "OS"}, {"number": 2}, record]
    tasks = BackgroundTasks()
    enqueue = MagicMock()
    monkeypatch.setattr(documents, "enqueue_document", enqueue)
    documents.queue_document(tasks, pdf, 1, 12, "Memory", DOCUMENT_ID)
    backend.ingest.assert_not_called()
    enqueue.assert_called_once()
    assert enqueue.call_args.args[1][0] == pdf


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
    monkeypatch.setattr(documents, "MAX_UPLOAD_BYTES", len(pdf) - 1)
    assert post_pdf(client, pdf).status_code == 413
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


@pytest.mark.parametrize("extra,expected", [(-1, 202), (0, 202), (1, 413)])
def test_upload_enforces_actual_40_mb_boundary(client, backend, record, monkeypatch, extra, expected):
    limit = 40 * 1024 * 1024
    assert documents.MAX_UPLOAD_BYTES == limit
    queue = MagicMock(return_value=record)
    monkeypatch.setattr(documents, "queue_document", queue)
    # Bypass parsing to isolate the real byte boundary without embedding a 40 MB file.
    response = client.post(
        "/documents", files={"file": ("large.pdf", b"%PDF-" + b" " * (limit + extra - 5), "application/pdf")},
        data={"subject_id": 1, "module_id": 12, "title": "Large lecture"},
    )
    assert response.status_code == expected
    if expected == 202:
        assert queue.call_count == 1
    else:
        assert "40 MB" in response.json()["detail"]
        queue.assert_not_called()
    backend.upload.assert_not_called()
    backend.ingest.assert_not_called()


def make_pptx_bytes(with_slide=True):
    presentation = Presentation()
    if with_slide:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.notes_slide.notes_text_frame.text = "Useful speaker notes from the lecture."
    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def test_pptx_upload_stores_original_format_and_uses_shared_ingest(client, backend, record, monkeypatch):
    enqueue = MagicMock()
    monkeypatch.setattr(documents, "enqueue_document", enqueue)
    content = make_pptx_bytes()
    backend.cursor.fetchone.side_effect = [{"code": "OS"}, {"number": 2}, record]
    response = client.post(
        "/documents", files={"file": ("lecture.PPTX", content, documents.PPTX_CONTENT_TYPE)},
        data={"subject_id": 1, "module_id": 12, "title": "Lecture"},
    )
    assert response.status_code == 202
    assert response.json()["file_type"] == "pptx"
    backend.upload.assert_called_once_with(content, f"official/OS/module-2/{DOCUMENT_ID}.pptx")
    assert enqueue.call_args.args[1] == (content, DOCUMENT_ID, "OS", 2, "Lecture", "pptx")


@pytest.mark.parametrize("filename,content", [
    ("lecture.ppt", b"old binary PowerPoint"),
    ("lecture.pptx", b"PK not a PowerPoint archive"),
    ("lecture.pptx", b"not a zip archive"),
    ("lecture.pptx", make_pptx_bytes(with_slide=False)),
], ids=["old-ppt", "corrupt-zip", "wrong-signature", "empty-presentation"])
def test_invalid_powerpoint_is_rejected_before_storage(client, backend, filename, content):
    response = client.post(
        "/documents", files={"file": (filename, content, documents.PPTX_CONTENT_TYPE)},
        data={"subject_id": 1, "module_id": 12, "title": "Lecture"},
    )
    assert response.status_code == 400
    if filename.endswith(".ppt"):
        assert "Save as .pptx" in response.json()["detail"]
    backend.upload.assert_not_called()
    backend.ingest.assert_not_called()


def test_pptx_download_url_uses_original_file(client, backend, record):
    path = "official/OS/lecture.pptx"
    backend.cursor.fetchone.return_value = {**record, "file_type": "pptx", "storage_path": path}
    assert client.get(f"/documents/{DOCUMENT_ID}/file-url").status_code == 200
    backend.sign.assert_called_once_with(path)


def test_storage_uses_powerpoint_mime_type(monkeypatch):
    bucket = MagicMock()
    monkeypatch.setattr(storage, "_bucket", lambda: bucket)
    storage.upload_document(b"fake-pptx", "official/lecture.pptx")
    bucket.upload.assert_called_once_with(
        "official/lecture.pptx", b"fake-pptx", file_options={"content-type": documents.PPTX_CONTENT_TYPE},
    )


def test_empty_pptx_upload_returns_readable_error(client, backend):
    response = client.post(
        "/documents", files={"file": ("empty.pptx", make_pptx_bytes(with_slide=False), documents.PPTX_CONTENT_TYPE)},
        data={"subject_id": 1, "module_id": 12, "title": "Empty lecture"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "No readable text found in slides"
    backend.upload.assert_not_called()
    backend.ingest.assert_not_called()


def test_background_failure_saves_safe_reason_visible_in_status(client, backend, record):
    from app.ingest.pipeline import IngestError
    reason = "No readable text found in slides"
    backend.ingest.side_effect = IngestError(reason, safe_reason=reason)
    documents.finish_upload(b"fake", DOCUMENT_ID, "OS", 2, "Lecture", "pptx")
    assert backend.cursor.execute.call_args.args[1] == (reason, DOCUMENT_ID)
    backend.cursor.fetchone.return_value = {**record, "status": "failed", "error": reason}
    response = client.get(f"/documents/{DOCUMENT_ID}")
    assert response.status_code == 200
    assert response.json()["error"] == reason


def test_background_failure_logs_chained_exception_without_secrets(backend, caplog):
    def fail(*args, **kwargs):
        try:
            raise ValueError("postgresql://user:fake-password@private/db")
        except ValueError as cause:
            raise RuntimeError("https://private.invalid?token=fake-token") from cause
    backend.ingest.side_effect = fail
    documents.finish_upload(b"fake", DOCUMENT_ID, "OS", 2, "Lecture", "pptx")
    assert "Caused by:" in caplog.text
    assert "RuntimeError" in caplog.text and "ValueError" in caplog.text
    for value in ("fake-password", "fake-token", "https://", "postgresql://"):
        assert value not in caplog.text


@pytest.fixture
def deletion_data(backend, monkeypatch):
    # Real local transactions verify row/chunk/cache rollback without accessing Supabase.
    database = sqlite3.connect(":memory:", check_same_thread=False)
    database.row_factory = sqlite3.Row
    database.executescript("""
        pragma foreign_keys = on;
        create table modules (id integer primary key);
        create table documents (id text primary key, subject_id integer, module_id integer, storage_path text);
        create table chunks (id integer, document_id text references documents(id) on delete cascade, embedding text);
        create table answer_cache (subject_id integer, answer text);
        insert into modules values (12);
    """)
    path = f"official/OS/module-2/{DOCUMENT_ID}.pdf"
    database.execute("insert into documents values (?, 1, 12, ?)", (str(DOCUMENT_ID), path))
    database.execute("insert into documents values ('other-document', 2, 12, null)")
    database.execute("insert into chunks values (1, ?, 'fake-vector')", (str(DOCUMENT_ID),))
    database.execute("insert into chunks values (2, 'other-document', 'other-vector')")
    database.execute("insert into answer_cache values (1, 'old answer')")
    database.execute("insert into answer_cache values (2, 'another subject answer')")
    database.commit()
    current = [None]
    failures = {"commit": False, "sql": False}

    def execute(query, params=()):
        if failures["sql"] and query.startswith("delete from documents"):
            raise RuntimeError("fake-db-error https://private.invalid?token=fake-token")
        params = tuple(str(value) if isinstance(value, UUID) else value for value in params)
        current[0] = database.execute(query.replace("%s", "?").replace(" for update", ""), params)

    backend.cursor.execute.side_effect = execute
    backend.cursor.fetchone.side_effect = lambda: current[0].fetchone()
    backend.cursor.__enter__.return_value = backend.cursor

    @contextmanager
    def transaction():
        try:
            yield SimpleNamespace(cursor=lambda **kwargs: backend.cursor)
            if failures["commit"]:
                raise RuntimeError("fake-commit-error")
            database.commit()
        except Exception:
            database.rollback()
            raise

    files = {path: b"original-file"}
    download = MagicMock(side_effect=lambda name: files[name])
    restore = MagicMock(side_effect=lambda content, name: files.update({name: content}))
    backend.remove.side_effect = lambda name: files.pop(name, None)
    monkeypatch.setattr(documents, "get_conn", transaction)
    monkeypatch.setattr(documents, "download_document", download)
    monkeypatch.setattr(documents, "restore_document", restore)
    yield SimpleNamespace(database=database, files=files, path=path, download=download,
                          restore=restore, failures=failures)
    database.close()


def test_admin_delete_removes_file_document_chunks_and_subject_cache(client, backend, deletion_data):
    response = client.delete(f"/documents/{DOCUMENT_ID}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": str(DOCUMENT_ID)}
    assert deletion_data.files == {}
    backend.remove.assert_called_once_with(deletion_data.path)
    assert deletion_data.database.execute("select id from documents").fetchall()[0][0] == "other-document"
    assert [row["document_id"] for row in deletion_data.database.execute("select * from chunks")] == ["other-document"]
    assert [row["subject_id"] for row in deletion_data.database.execute("select * from answer_cache")] == [2]
    deletion_data.restore.assert_not_called()


@pytest.mark.parametrize("role", ["student", "rep"])
def test_non_admin_delete_returns_403_without_mutation(client, backend, deletion_data, role):
    main.app.dependency_overrides[get_current_user] = lambda: {
        "id": DOCUMENT_ID, "email": "student@dxb.manipal.edu", "role": role,
    }
    assert client.delete(f"/documents/{DOCUMENT_ID}").status_code == 403
    backend.cursor.execute.assert_not_called()
    backend.remove.assert_not_called()
    deletion_data.download.assert_not_called()
    assert deletion_data.files[deletion_data.path] == b"original-file"


def test_delete_missing_id_returns_404(client, backend, deletion_data):
    response = client.delete("/documents/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404
    backend.remove.assert_not_called()
    deletion_data.download.assert_not_called()


def assert_delete_was_rolled_back(data):
    assert data.database.execute("select count(*) from documents").fetchone()[0] == 2
    assert data.database.execute("select count(*) from chunks").fetchone()[0] == 2
    assert data.database.execute("select count(*) from answer_cache").fetchone()[0] == 2
    assert data.files[data.path] == b"original-file"


def test_database_delete_failure_keeps_file_and_rolls_back_all_rows(client, backend, deletion_data, caplog):
    deletion_data.failures["sql"] = True
    response = client.delete(f"/documents/{DOCUMENT_ID}")
    assert response.status_code == 503
    assert response.json()["detail"] == documents.DELETE_FAILED
    assert_delete_was_rolled_back(deletion_data)
    backend.remove.assert_not_called()
    assert "Document deletion failed" in caplog.text
    assert "fake-token" not in caplog.text + response.text
    assert "https://" not in caplog.text + response.text


def test_storage_timeout_after_removal_restores_file_and_rolls_back_sql(client, backend, deletion_data):
    def uncertain_remove(path):
        deletion_data.files.pop(path)
        raise RuntimeError("fake-storage-timeout")
    backend.remove.side_effect = uncertain_remove
    response = client.delete(f"/documents/{DOCUMENT_ID}")
    assert response.status_code == 503
    assert_delete_was_rolled_back(deletion_data)
    deletion_data.restore.assert_called_once_with(b"original-file", deletion_data.path)


def test_commit_failure_restores_file_and_rolls_back_sql(client, deletion_data):
    deletion_data.failures["commit"] = True
    assert client.delete(f"/documents/{DOCUMENT_ID}").status_code == 503
    assert_delete_was_rolled_back(deletion_data)


def test_backup_failure_prevents_any_deletion(client, backend, deletion_data):
    deletion_data.download.side_effect = RuntimeError("fake-download-failure")
    assert client.delete(f"/documents/{DOCUMENT_ID}").status_code == 503
    assert_delete_was_rolled_back(deletion_data)
    backend.remove.assert_not_called()


def test_restore_failure_is_logged_and_returns_explicit_recovery_error(client, backend, deletion_data, caplog):
    backend.remove.side_effect = RuntimeError("fake-remove-error")
    deletion_data.restore.side_effect = RuntimeError("fake-restore-error")
    response = client.delete(f"/documents/{DOCUMENT_ID}")
    assert response.status_code == 503
    assert response.json()["detail"] == documents.DELETE_RECOVERY_FAILED
    assert "Could not restore document file" in caplog.text
    assert_delete_was_rolled_back(deletion_data)


def test_delete_document_without_storage_path_still_removes_rows(client, backend, deletion_data):
    deletion_data.database.execute("update documents set storage_path = null where id = ?", (str(DOCUMENT_ID),))
    deletion_data.database.commit()
    assert client.delete(f"/documents/{DOCUMENT_ID}").status_code == 200
    deletion_data.download.assert_not_called()
    backend.remove.assert_not_called()
    assert deletion_data.database.execute("select count(*) from chunks").fetchone()[0] == 1


def test_browser_cors_allows_delete(client):
    response = client.options(f"/documents/{DOCUMENT_ID}", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "authorization",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_storage_backup_and_restore_helpers_use_private_bucket(monkeypatch):
    bucket = MagicMock()
    bucket.download.return_value = b"original-file"
    monkeypatch.setattr(storage, "_bucket", lambda: bucket)
    assert storage.download_document("official/lecture.pptx") == b"original-file"
    storage.restore_document(b"original-file", "official/lecture.pptx")
    bucket.upload.assert_called_once_with("official/lecture.pptx", b"original-file", file_options={
        "content-type": documents.PPTX_CONTENT_TYPE, "upsert": "true",
    })



def test_subject_overview_returns_documents_and_usage(client, backend, monkeypatch, record):
    backend.cursor.fetchone.return_value = {"id": 1, "code": "OS", "name": "Operating Systems"}
    backend.cursor.fetchall.side_effect = [[{"id": 12, "subject_id": 1, "number": 2, "title": "Memory"}], [{**record, "module_id": 12}]]
    monkeypatch.setattr(subjects.quota, "user_usage", lambda user_id: {"used": 1, "limit": 5, "resets_at": "tomorrow"})
    result = client.get("/subjects/1/overview")
    assert result.status_code == 200
    assert result.json()["documents"][0]["module_id"] == 12
    assert result.json()["usage"]["used"] == 1


def test_cors_preflight_is_cached(client):
    result = client.options("/ask", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert result.headers["access-control-max-age"] == "86400"


def test_followup_bypasses_shared_cache(client, backend, monkeypatch):
    backend.cursor.fetchone.return_value = (1,)
    lookup = MagicMock()
    store = MagicMock()
    monkeypatch.setattr(ask.cache, "get", lookup)
    monkeypatch.setattr(ask.cache, "put", store)
    response = client.post("/ask", json={"question": "Explain it", "subject_id": 1,
                            "mode": "strict", "history": [{"role": "user", "content": "What is paging?"}]})
    assert response.status_code == 200
    lookup.assert_not_called()
    store.assert_not_called()
    assert backend.generate.call_args.kwargs["history"][0]["content"] == "What is paging?"


def test_small_talk_skips_retrieval_and_accounts_for_model_call(client, backend, monkeypatch):
    backend.cursor.fetchone.return_value = (1,)
    talk = MagicMock(return_value={"answer": "Hello!", "sources": [], "usage": {"input_tokens": 4, "output_tokens": 2}})
    monkeypatch.setattr(ask, "answer_small_talk", talk)
    result = client.post("/ask", json={"question": "Hi!", "subject_id": 1})
    assert result.status_code == 200
    assert result.json()["sources"] == []
    backend.generate.assert_not_called()
    ask.quota.record_usage.assert_called_once()


def test_presentation_viewer_returns_requested_slide(client, monkeypatch):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(10000, 20000, 300000, 400000).text_frame.text = "Paging"
    output = BytesIO()
    presentation.save(output)
    monkeypatch.setattr(documents, "get_document", lambda document_id: {"storage_path": "notes/test.pptx"})
    monkeypatch.setattr(documents, "download_document", lambda path: output.getvalue())
    response = client.get(f"/documents/{DOCUMENT_ID}/slides/1")
    assert response.status_code == 200
    assert response.json()["shapes"][0]["text"] == "Paging"
    assert response.json()["total"] == 1
    assert client.get(f"/documents/{DOCUMENT_ID}/slides/2").status_code == 404


def test_powerpoint_preview_returns_converted_pdf(client, monkeypatch):
    monkeypatch.setattr(documents, "get_document", lambda document_id: {"storage_path": "notes/test.pptx"})
    monkeypatch.setattr(documents, "download_document", lambda path: b"original-pptx")
    convert = MagicMock(return_value=b"%PDF-fake")
    monkeypatch.setattr(documents, "convert_presentation", convert)
    response = client.get(f"/documents/{DOCUMENT_ID}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-fake"
    convert.assert_called_once_with(b"original-pptx")


def test_powerpoint_converter_requires_libreoffice(monkeypatch):
    monkeypatch.setattr(documents.shutil, "which", lambda name: None)
    monkeypatch.setattr(documents.Path, "is_file", lambda self: False)
    with pytest.raises(documents.HTTPException) as error:
        documents.convert_presentation(b"presentation")
    assert error.value.status_code == 503


def test_converter_uses_isolated_profile_and_cleans_temporary_files(monkeypatch):
    monkeypatch.setattr(documents.shutil, "which", lambda name: "soffice")
    seen = {}
    def convert(command, **kwargs):
        source = documents.Path(command[-1])
        seen["folder"] = source.parent
        assert source.read_bytes() == b"pptx-data"
        assert "--headless" in command
        assert any(part.startswith("-env:UserInstallation=") for part in command)
        assert kwargs["timeout"] == 120
        (source.parent / "presentation.pdf").write_bytes(b"%PDF-converted")
    monkeypatch.setattr(documents.subprocess, "run", convert)
    assert documents.convert_presentation(b"pptx-data") == b"%PDF-converted"
    assert not seen["folder"].exists()


def test_personal_answers_bypass_shared_cache(client, backend, monkeypatch):
    backend.cursor.fetchone.return_value = (1,)
    monkeypatch.setattr(ask, "has_note", lambda user_id, subject_id: True)
    lookup = MagicMock()
    store = MagicMock()
    monkeypatch.setattr(ask.cache, "get", lookup)
    monkeypatch.setattr(ask.cache, "put", store)
    response = client.post("/ask", json={"question": "paging", "subject_id": 1})
    assert response.status_code == 200
    lookup.assert_not_called()
    store.assert_not_called()
    assert backend.generate.call_args.kwargs["user_id"] == DOCUMENT_ID


def test_note_file_cannot_be_opened_by_other_users(client, monkeypatch):
    from app.routers import notes
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = None
    monkeypatch.setattr(notes, "get_conn", context)
    bucket = MagicMock()
    monkeypatch.setattr(notes, "personal_bucket", bucket)
    response = client.get(f"/notes/{DOCUMENT_ID}/file-url")
    assert response.status_code == 404
    assert cursor.execute.call_args.args[1] == (DOCUMENT_ID, DOCUMENT_ID)
    bucket.assert_not_called()


def test_note_replacement_storage_failure_restores_old_file(monkeypatch):
    from app.routers import notes
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [(1,), ("owner/old.png", "image")]
    monkeypatch.setattr(notes, "get_conn", context)
    monkeypatch.setattr(notes, "validate_file", lambda *args: (".png", "image", "image/png"))
    monkeypatch.setattr(notes, "transcribe", lambda *args: [{"page": 1, "text": "Personal handwritten notes"}])
    embed = MagicMock(return_value=[[0.0] * 768])
    monkeypatch.setattr(notes, "embed_documents", embed)
    monkeypatch.setattr(notes, "Settings", lambda: SimpleNamespace(embedding_model="test-model"))
    bucket = MagicMock()
    bucket.download.return_value = b"old image"
    bucket.remove.side_effect = [RuntimeError("storage failure"), None]
    monkeypatch.setattr(notes, "personal_bucket", lambda: bucket)
    with pytest.raises(notes.HTTPException) as error:
        notes.save_note(b"new image", "new.png", 1, True, "owner")
    assert error.value.status_code == 503
    assert embed.call_args.args[0] == ["Personal handwritten notes"]
    assert bucket.upload.call_args_list[1].args[:2] == ("owner/old.png", b"old image")


def test_note_limit_rejected_before_ocr(monkeypatch):
    from app.routers import notes
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (1,)
    monkeypatch.setattr(notes, "get_conn", context)
    monkeypatch.setattr(notes, "validate_file", lambda *args: (".png", "image", "image/png"))
    monkeypatch.setattr(notes, "has_note", lambda *args: True)
    ocr = MagicMock()
    monkeypatch.setattr(notes, "transcribe", ocr)
    with pytest.raises(notes.HTTPException) as error:
        notes.save_note(b"image", "note.png", 1, False, "owner")
    assert error.value.status_code == 409
    ocr.assert_not_called()


def test_course_figure_requires_ready_official_document(client, backend):
    backend.cursor.fetchone.return_value = {"image_data": b"fake-jpeg", "content_type": "image/jpeg"}
    result = client.get(f"/figures/{DOCUMENT_ID}")
    assert result.status_code == 200
    assert result.content == b"fake-jpeg"
    sql, params = backend.cursor.execute.call_args.args
    assert "d.source_type = 'official'" in sql and "d.status = 'ready'" in sql
    assert params == (DOCUMENT_ID,)


def test_admin_can_add_subject_with_modules(client, backend):
    backend.cursor.fetchone.return_value = {"id": 9, "code": "AI", "name": "Artificial Intelligence"}
    result = client.post("/subjects", json={"code": " ai ", "name": "Artificial Intelligence"})
    assert result.status_code == 201
    assert result.json()["code"] == "AI"
    assert backend.cursor.executemany.call_args.args[1] == [(9, n, f"Module {n}") for n in range(1, 6)]


def test_student_cannot_add_subject(client, backend):
    main.app.dependency_overrides[get_current_user] = lambda: {"id": DOCUMENT_ID, "email": "student@dxb.manipal.edu", "role": "student"}
    result = client.post("/subjects", json={"code": "AI", "name": "Artificial Intelligence"})
    assert result.status_code == 403
    backend.cursor.execute.assert_not_called()


def test_duplicate_subject_code_is_reported(client, backend):
    backend.cursor.execute.side_effect = subjects.UniqueViolation()
    result = client.post("/subjects", json={"code": "AI", "name": "Artificial Intelligence"})
    assert result.status_code == 409


def test_note_processing_reports_stages_and_owner(client, monkeypatch):
    from app.routers import notes
    observed = []
    def save(data, filename, subject_id, replace, user_id, progress):
        assert subject_id == 4 and user_id == DOCUMENT_ID
        progress("reading", 2)
        observed.append(next(iter(notes._jobs.values()))["stage"])
        progress("indexing", 2)
        observed.append(next(iter(notes._jobs.values()))["stage"])
        return {"subject_id": subject_id}
    notes._jobs.clear()
    monkeypatch.setattr(notes, "save_note", save)
    response = client.post("/notes/jobs", data={"subject_id": "4", "replace": "false"},
                           files={"file": ("notes.png", b"fake", "image/png")})
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert observed == ["reading", "indexing"]
    assert client.get(f"/notes/jobs/{job_id}").json()["stage"] == "ready"
    with pytest.raises(notes.HTTPException) as error:
        notes.job_status(job_id, {"id": "other-user"})
    assert error.value.status_code == 404
    notes._jobs.clear()


def test_admin_delete_subject_removes_official_and_private_files(client, backend, monkeypatch):
    cursor = backend.cursor
    cursor.fetchone.return_value = {"id": 4}
    cursor.fetchall.side_effect = [[], [{"storage_path": "official/test.pdf"}],
                                    [{"storage_path": "user/note.png", "file_type": "image"}]]
    download = MagicMock(return_value=b"official")
    remove = MagicMock()
    bucket = MagicMock()
    bucket.download.return_value = b"private"
    monkeypatch.setattr(subjects, "download_document", download)
    monkeypatch.setattr(subjects, "delete_document", remove)
    monkeypatch.setattr(subjects, "personal_bucket", lambda: bucket)
    response = client.delete("/subjects/4")
    assert response.status_code == 200
    remove.assert_called_once_with("official/test.pdf")
    bucket.remove.assert_called_once_with(["user/note.png"])
    sql = " ".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "delete from personal_notes" in sql and "delete from documents" in sql and "delete from subjects" in sql


def test_scope_deletion_restores_files_after_storage_failure(client, backend, monkeypatch):
    cursor = backend.cursor
    cursor.fetchone.return_value = {"id": 4}
    cursor.fetchall.side_effect = [[], [{"storage_path": "official/test.pdf"}],
                                    [{"storage_path": "user/note.png", "file_type": "image"}]]
    monkeypatch.setattr(subjects, "download_document", lambda path: b"official")
    remove = MagicMock()
    restore = MagicMock()
    bucket = MagicMock()
    bucket.download.return_value = b"private"
    bucket.remove.side_effect = RuntimeError("storage failure")
    monkeypatch.setattr(subjects, "delete_document", remove)
    monkeypatch.setattr(subjects, "restore_document", restore)
    monkeypatch.setattr(subjects, "personal_bucket", lambda: bucket)
    response = client.delete("/subjects/4")
    assert response.status_code == 503
    restore.assert_called_once_with(b"official", "official/test.pdf")
    assert bucket.upload.called


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/subjects/1/modules", {"number": 6, "title": "Concurrency"}),
    ("PUT", "/modules/12", {"title": "Concurrency"}),
    ("DELETE", "/modules/12", None),
    ("DELETE", "/subjects/1", None),
])
def test_scope_management_requires_admin(client, backend, method, path, body):
    main.app.dependency_overrides[get_current_user] = lambda: {"id": DOCUMENT_ID, "email": "student@dxb.manipal.edu", "role": "student"}
    response = client.request(method, path, json=body)
    assert response.status_code == 403
    backend.cursor.execute.assert_not_called()


def test_admin_add_and_rename_module(client, backend):
    backend.cursor.fetchone.side_effect = [{"id": 1}, {"id": 12, "subject_id": 1, "number": 6, "title": "Threads"}]
    response = client.post("/subjects/1/modules", json={"number": 6, "title": "Threads"})
    assert response.status_code == 201 and response.json()["number"] == 6
    backend.cursor.fetchone.side_effect = None
    backend.cursor.fetchone.return_value = {"id": 12, "subject_id": 1, "number": 6, "title": "Concurrency"}
    response = client.put("/modules/12", json={"title": "Concurrency"})
    assert response.status_code == 200 and response.json()["title"] == "Concurrency"


def test_admin_delete_module_removes_documents_but_not_personal_notes(client, backend, monkeypatch):
    cursor = backend.cursor
    cursor.fetchone.return_value = {"subject_id": 4}
    cursor.fetchall.return_value = [{"storage_path": "official/module.pdf"}]
    monkeypatch.setattr(subjects, "download_document", lambda path: b"file")
    remove = MagicMock()
    personal = MagicMock()
    monkeypatch.setattr(subjects, "delete_document", remove)
    monkeypatch.setattr(subjects, "personal_bucket", personal)
    response = client.delete("/modules/12")
    assert response.status_code == 200
    remove.assert_called_once_with("official/module.pdf")
    personal.assert_not_called()
    sql = " ".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "delete from documents where module_id" in sql
    assert "delete from modules" in sql
    assert "delete from personal_notes" not in sql


def test_upload_queue_runs_one_at_a_time_and_continues_after_failure(monkeypatch):
    from queue import Queue
    from uuid import uuid4
    from app.routers import documents
    import time
    queue = Queue()
    monkeypatch.setattr(documents, "_queue", queue)
    monkeypatch.setattr(documents, "_queue_items", {})
    monkeypatch.setattr(documents, "_worker_started", False)
    seen = []
    def finish(data, document_id, *args):
        seen.append(data)
        if data == b"first":
            raise RuntimeError("failure")
    monkeypatch.setattr(documents, "finish_upload", finish)
    monkeypatch.setattr(documents, "get_document", lambda document_id: {"status": "ready", "error": None})
    first, second = uuid4(), uuid4()
    documents.enqueue_document({"id": first}, (b"first", first, "OS", 1, "One", "pdf"))
    documents.enqueue_document({"id": second}, (b"second", second, "OS", 1, "Two", "pdf"))
    queue.join()
    assert seen == [b"first", b"second"]
    assert documents._queue_items[first]["queue_status"] == "failed"
    assert documents._queue_items[second]["queue_status"] == "ready"


def test_upload_queue_requires_admin(client):
    main.app.dependency_overrides[get_current_user] = lambda: {"id": DOCUMENT_ID, "email": "student@dxb.manipal.edu", "role": "student"}
    assert client.get("/admin/upload-queue").status_code == 403
    assert client.post(f"/admin/upload-queue/{DOCUMENT_ID}/retry").status_code == 403


def test_retry_failed_upload_requeues_stored_file(monkeypatch):
    from queue import Queue
    from app.routers import documents
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"title": "Lecture", "storage_path": "official/test.pdf", "code": "OS", "number": 2}
    cursor.rowcount = 1
    queue = Queue()
    item = {"id": DOCUMENT_ID, "queue_status": "failed", "status": "failed", "error": "failed"}
    monkeypatch.setattr(documents, "_queue_items", {DOCUMENT_ID: item})
    monkeypatch.setattr(documents, "_queue", queue)
    monkeypatch.setattr(documents, "get_conn", context)
    monkeypatch.setattr(documents, "download_document", lambda path: b"stored")
    assert documents.retry_upload(DOCUMENT_ID, {"role": "admin"}) == {"queued": True}
    assert queue.get_nowait() == (b"stored", DOCUMENT_ID, "OS", 2, "Lecture", "pdf")
    assert item["queue_status"] == "queued" and item["error"] is None


def test_worksheet_extraction_preserves_unknown_fields(monkeypatch):
    from app.routers import worksheets
    from pydantic import SecretStr
    import json
    config = SimpleNamespace(chat_model="google_genai:gemini-3.5-flash-lite", google_api_key=SecretStr("fake-key"))
    monkeypatch.setattr(worksheets, "Settings", lambda: config)
    payload = {"questions": [{"question_text": "Explain paging", "question_number": "1", "module_number": None, "year": None, "marks": None, "question_type": "short"}]}
    response = SimpleNamespace(status_code=200, json=lambda: {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
    post = MagicMock(return_value=response)
    monkeypatch.setattr(worksheets.httpx, "post", post)
    assert worksheets.extract_questions([(b"image", "image/png")]) == [(None, None, "1", None, "short", "Explain paging")]
    assert post.call_count == 1


def test_worksheet_without_evidence_never_calls_model(monkeypatch):
    from app.routers import worksheets
    monkeypatch.setattr(worksheets, "retrieve", lambda *args: [])
    model = MagicMock()
    monkeypatch.setattr(worksheets, "get_chat_model", model)
    answer, sources = worksheets.answer_one("Question", 1, "normal", None)
    assert answer == worksheets.NOT_FOUND and sources == []
    model.assert_not_called()


def test_worksheet_owner_check_precedes_questions(client, monkeypatch):
    from app.routers import worksheets
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = None
    monkeypatch.setattr(worksheets, "get_conn", context)
    assert client.get(f"/worksheets/{DOCUMENT_ID}").status_code == 404
    assert cursor.execute.call_count == 1
    assert cursor.execute.call_args.args[1] == (DOCUMENT_ID, DOCUMENT_ID)


def test_worksheet_stores_all_questions_before_answering(monkeypatch):
    from app.routers import worksheets
    connection = MagicMock()
    cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [(10,), (11,)]
    monkeypatch.setattr(worksheets, "get_conn", connection)
    monkeypatch.setattr(worksheets, "extract_questions", lambda *args: [(None, None, "1", None, None, "First"), (None, None, "2", None, None, "Second")])
    answered = []
    def answer(worksheet_id, question_id, user_id, api_key):
        inserts = [call for call in cursor.execute.call_args_list if "insert into worksheet_questions" in call.args[0]]
        assert len(inserts) == 2
        answered.append(question_id)
    monkeypatch.setattr(worksheets, "answer_question_job", answer)
    worksheets.run_worksheet(DOCUMENT_ID, DOCUMENT_ID, [])
    assert answered == [10, 11]


def test_worksheet_question_failure_is_saved_without_raw_error(monkeypatch):
    from app.routers import worksheets
    connection = MagicMock()
    cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"question_text": "private", "subject_id": 1, "mode": "normal"}
    monkeypatch.setattr(worksheets, "get_conn", connection)
    monkeypatch.setattr(worksheets, "answer_one", MagicMock(side_effect=RuntimeError("private secret")))
    worksheets.answer_question_job(DOCUMENT_ID, 1, DOCUMENT_ID)
    params = cursor.execute.call_args.args[1]
    assert "private secret" not in str(params)
    assert "failed" in cursor.execute.call_args.args[0]


def test_worksheet_server_calls_respect_quota_and_byok(monkeypatch):
    from app.routers import worksheets
    from pydantic import SecretStr
    monkeypatch.setattr(worksheets.quota, "dubai_day", lambda: "today")
    consume = MagicMock(return_value=False)
    monkeypatch.setattr(worksheets.quota, "try_consume", consume)
    with pytest.raises(worksheets.WorksheetQuotaExceeded):
        worksheets.reserve_call(DOCUMENT_ID, None)
    assert worksheets.reserve_call(DOCUMENT_ID, SecretStr("dummy")) is None
    consume.assert_called_once_with(DOCUMENT_ID, "today")


def test_worksheet_quota_pause_keeps_question_queued(monkeypatch):
    from app.routers import worksheets
    context = MagicMock()
    cursor = context.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"question_text": "private", "subject_id": 1, "mode": "normal", "marks": 3, "question_type": "short"}
    monkeypatch.setattr(worksheets, "get_conn", context)
    monkeypatch.setattr(worksheets, "answer_one", MagicMock(side_effect=worksheets.WorksheetQuotaExceeded()))
    assert worksheets.answer_question_job(DOCUMENT_ID, 1, DOCUMENT_ID) is False
    assert "status='queued'" in cursor.execute.call_args.args[0]


def test_worksheet_answer_records_server_token_usage(monkeypatch):
    from app.routers import worksheets
    hit = {"document_id": DOCUMENT_ID, "document": "Lecture", "page": 1, "module": 1, "subject": "OS", "score": 0.9, "content": "example", "file_type": "pdf"}
    monkeypatch.setattr(worksheets, "retrieve", lambda *args: [hit])
    monkeypatch.setattr(worksheets, "Settings", lambda: SimpleNamespace(max_context_tokens=1000))
    monkeypatch.setattr(worksheets.quota, "dubai_day", lambda: "today")
    consume = MagicMock(return_value=True)
    record = MagicMock()
    monkeypatch.setattr(worksheets.quota, "try_consume", consume)
    monkeypatch.setattr(worksheets.quota, "record_usage", record)
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="Answer [1]", usage_metadata={"input_tokens": 12, "output_tokens": 5})
    monkeypatch.setattr(worksheets, "get_chat_model", lambda *args: model)
    answer, sources = worksheets.answer_one("Question", 1, "strict", None, DOCUMENT_ID, 3, "short")
    assert answer == "Answer [1]" and len(sources) == 1
    consume.assert_called_once_with(DOCUMENT_ID, "today")
    record.assert_called_once_with(DOCUMENT_ID, 12, 5, day="today")


@pytest.mark.parametrize("marks, expected", [
    (1, "2 to 4 key points"), (2, "2 to 4 key points"),
    (3, "three clear points"), (4, "structured answer"),
    (5, "structured answer"), (12, "structured answer"),
    (45, "structured answer"),
])
def test_worksheet_answer_uses_mark_ranges(monkeypatch, marks, expected):
    from app.routers import worksheets
    hit = {"document_id": DOCUMENT_ID, "document": "Lecture", "page": 1, "module": 1,
           "subject": "OS", "score": 0.9, "content": "example", "file_type": "pdf"}
    monkeypatch.setattr(worksheets, "retrieve", lambda *args: [hit])
    monkeypatch.setattr(worksheets, "Settings", lambda: SimpleNamespace(max_context_tokens=1000))
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="Answer [1]", usage_metadata={})
    monkeypatch.setattr(worksheets, "get_chat_model", lambda *args: model)
    worksheets.answer_one("Question", 1, "normal", "dummy", marks=marks)
    instruction = model.invoke.call_args.args[0][0][1]
    assert expected in instruction


def test_worksheet_chat_selects_multiple_question_numbers():
    from app.routers import worksheets
    rows = [{"id": 1, "position": 5, "question_number": "5"}, {"id": 2, "position": 6, "question_number": "6"}, {"id": 3, "position": 20, "question_number": "20"}]
    assert [row["id"] for row in worksheets.selected_questions(rows, "compare Q5 and Q6", None)] == [1, 2]
    assert [row["id"] for row in worksheets.selected_questions(rows, "explain 20 more simply", None)] == [3]
    assert worksheets.selected_questions(rows, "now even simpler", None) == rows


def test_worksheet_followup_uses_saved_answer_and_cited_evidence(monkeypatch):
    from app.routers import worksheets
    source = {"n": 1, "document_id": str(DOCUMENT_ID), "page": 2, "score": 0.9}
    row = {"question_text": "What is paging?", "answer": "Saved explanation [1]", "sources": [source]}
    hit = {"document_id": DOCUMENT_ID, "document": "Lecture", "page": 2, "module": 1, "subject": "OS", "score": 0.9, "content": "Evidence", "file_type": "pdf"}
    search = MagicMock(return_value=[])
    monkeypatch.setattr(worksheets, "retrieve", search)
    monkeypatch.setattr(worksheets, "previous_source_hits", lambda *args: [hit])
    monkeypatch.setattr(worksheets, "Settings", lambda: SimpleNamespace(max_context_tokens=1000))
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="Simpler explanation [1]", usage_metadata={})
    monkeypatch.setattr(worksheets, "get_chat_model", lambda *args: model)
    answer, sources = worksheets.chat_answer([row], [], 1, "normal", "explain this more simply", DOCUMENT_ID, "dummy")
    assert answer == "Simpler explanation [1]" and sources[0]["page"] == 2
    assert "What is paging?" in search.call_args.args[0]
    assert "explain this more simply" in search.call_args.args[0]
    assert "Saved explanation" in model.invoke.call_args.args[0][1][1]


def test_delete_worksheet_requires_owner_and_marks_cancelled(monkeypatch):
    from app.routers import worksheets
    from uuid import uuid4
    worksheet_id = uuid4()
    connection = MagicMock()
    cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (worksheet_id,)
    monkeypatch.setattr(worksheets, "get_conn", connection)
    monkeypatch.setattr(worksheets, "_deleted", set())
    assert worksheets.delete_worksheet(worksheet_id, {"id": DOCUMENT_ID}) == {"deleted": True}
    assert cursor.execute.call_args.args[1] == (worksheet_id, DOCUMENT_ID)
    assert worksheet_id in worksheets._deleted
    cursor.fetchone.return_value = None
    with pytest.raises(worksheets.HTTPException) as error:
        worksheets.delete_worksheet(uuid4(), {"id": DOCUMENT_ID})
    assert error.value.status_code == 404


def test_worksheet_chat_can_use_saved_answer_without_retrieval(monkeypatch):
    from app.routers import worksheets
    row = {"question_text": "Explain paging", "answer": "Saved answer", "sources": []}
    monkeypatch.setattr(worksheets, "retrieve", lambda *args: [])
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="A simpler saved answer", usage_metadata={})
    monkeypatch.setattr(worksheets, "get_chat_model", lambda *args: model)
    answer, sources = worksheets.chat_answer([row], [], 1, "normal", "simplify", DOCUMENT_ID, "dummy")
    assert answer.startswith("A simpler saved answer") and "No verified citations" in answer and sources == []
    assert "Saved answer" in model.invoke.call_args.args[0][1][1]
