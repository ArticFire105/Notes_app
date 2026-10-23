"""Exercise PDF loading, atomic ingestion, and CLI errors without live services.
Mock model calls and database contexts while checking stored metadata and rollback.
Use temporary dummy PDFs so no real notes, credentials, or .env are accessed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from pydantic import SecretStr
from pypdf import PdfWriter
import pytest

from app import db
from app.ingest import pdf_loader, pipeline
from scripts import ingest_pdf as cli


def test_loader_preserves_original_pages_and_counts_short_text(tmp_path, monkeypatch):
    source = tmp_path / "dummy.pdf"
    source.write_bytes(b"dummy")
    texts = ["A useful explanation of virtual memory and paging.", None, "Page 3", " " * 40,
             "A useful explanation of address translation and page tables."]
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in texts])
    monkeypatch.setattr(pdf_loader, "PdfReader", lambda stream: reader)
    pages, skipped = pdf_loader.load_pdf_pages(source)
    assert [page["page"] for page in pages] == [1, 5]
    assert skipped == 3


def test_real_blank_pdf_counts_every_page_as_skipped(tmp_path):
    source = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    with source.open("wb") as output:
        writer.write(output)
    assert pdf_loader.load_pdf_pages(source) == ([], 2)


@pytest.fixture
def ingestion(monkeypatch):
    monkeypatch.setattr(pipeline, "Settings", lambda: SimpleNamespace(embedding_model="test-model"))
    monkeypatch.setattr(pipeline, "load_pdf_pages", lambda path: ([{"page": 2, "text": "notes"}], 1))
    chunks = [{"page": 2, "chunk_index": i, "content": f"chunk {i}"} for i in range(65)]
    monkeypatch.setattr(pipeline, "chunk_pages", lambda pages: chunks)
    embed = MagicMock(side_effect=lambda texts: [[0.0] * 768 for text in texts])
    monkeypatch.setattr(pipeline, "embed_documents", embed)
    connection_context = MagicMock()
    connection = connection_context.return_value.__enter__.return_value
    cursor = connection.cursor.return_value.__enter__.return_value
    document_id = UUID("00000000-0000-0000-0000-000000000001")
    cursor.fetchone.side_effect = [(1, 2), None, (document_id,)]
    monkeypatch.setattr(pipeline, "get_conn", connection_context)
    return SimpleNamespace(
        embed=embed, context=connection_context, cursor=cursor,
        document_id=document_id, chunks=chunks,
    )


def test_ingestion_batches_and_stores_scope_and_original_page_count(ingestion, capsys):
    result = pipeline.ingest_pdf("dummy.pdf", "os", 2, "Memory")
    assert result == ingestion.document_id
    assert [len(call.args[0]) for call in ingestion.embed.call_args_list] == [32, 32, 1]
    calls = ingestion.cursor.execute.call_args_list
    assert calls[0].args[1] == ("OS", 2)
    assert "for update of modules" in calls[0].args[0]
    assert calls[2].args[1] == (1, 2, "official", "Memory", 2)
    rows = ingestion.cursor.executemany.call_args.args[1]
    assert len(rows) == 65
    assert rows[0][:7] == (result, 1, 2, "official", 2, 0, "chunk 0")
    assert rows[0][7].dimensions() == 768
    assert rows[0][8] == "test-model"
    ingestion.context.return_value.__exit__.assert_called_once_with(None, None, None)
    summary = capsys.readouterr().out
    assert "Pages read: 2" in summary and "chunks stored: 65" in summary
    assert "pages skipped (no usable text): 1" in summary and "seconds taken:" in summary


def test_duplicate_is_refused_without_writes(ingestion):
    ingestion.cursor.fetchone.side_effect = [(1, 2), (ingestion.document_id,)]
    with pytest.raises(pipeline.IngestError, match="--replace"):
        pipeline.ingest_pdf("dummy.pdf", "OS", 2, "Memory")
    ingestion.cursor.executemany.assert_not_called()
    assert len(ingestion.cursor.execute.call_args_list) == 2


def test_replace_deletes_old_document_in_same_transaction(ingestion):
    ingestion.cursor.fetchone.side_effect = [(1, 2), (ingestion.document_id,), (ingestion.document_id,)]
    pipeline.ingest_pdf("dummy.pdf", "OS", 2, "Memory", replace=True)
    calls = ingestion.cursor.execute.call_args_list
    assert calls[2].args == (
        "delete from documents where module_id = %s and title = %s", (2, "Memory")
    )
    assert "insert into documents" in calls[3].args[0]
    ingestion.context.assert_called_once()


def test_chunk_insert_failure_exits_transaction_with_error(ingestion, capsys):
    ingestion.cursor.fetchone.side_effect = [(1, 2), (ingestion.document_id,), (ingestion.document_id,)]
    ingestion.cursor.executemany.side_effect = RuntimeError("dummy failure")
    with pytest.raises(RuntimeError):
        pipeline.ingest_pdf("dummy.pdf", "OS", 2, "Memory", replace=True)
    assert ingestion.context.return_value.__exit__.call_args.args[0] is RuntimeError
    assert "chunks stored:" not in capsys.readouterr().out


def test_third_embedding_batch_failure_opens_no_database_transaction(ingestion):
    ingestion.embed.side_effect = [[[0.0] * 768] * 32, [[0.0] * 768] * 32, RuntimeError("dummy failure")]
    with pytest.raises(RuntimeError):
        pipeline.ingest_pdf("dummy.pdf", "OS", 2, "Memory")
    ingestion.context.assert_not_called()


def test_all_scanned_pages_are_reported_without_model_or_database(ingestion, monkeypatch):
    monkeypatch.setattr(pipeline, "load_pdf_pages", lambda path: ([], 3))
    monkeypatch.setattr(pipeline, "chunk_pages", lambda pages: [])
    with pytest.raises(pipeline.IngestError, match="pages read=3, pages skipped=3"):
        pipeline.ingest_pdf("dummy.pdf", "OS", 2, "Memory")
    ingestion.embed.assert_not_called()
    ingestion.context.assert_not_called()


def test_unknown_scope_is_refused_without_writes(ingestion):
    ingestion.cursor.fetchone.side_effect = [None]
    with pytest.raises(pipeline.IngestError, match="Subject/module not found"):
        pipeline.ingest_pdf("dummy.pdf", "OS", 99, "Memory")
    ingestion.cursor.executemany.assert_not_called()


def test_connection_registers_vectors_and_forwards_error_to_driver(monkeypatch):
    settings = SimpleNamespace(database_url=SecretStr("dummy-db-url"))
    monkeypatch.setattr(db, "Settings", lambda: settings)
    connect = MagicMock()
    register = MagicMock()
    monkeypatch.setattr(db.psycopg, "connect", connect)
    monkeypatch.setattr(db, "register_vector", register)
    with pytest.raises(RuntimeError, match="dummy failure"):
        with db.get_conn() as connection:
            register.assert_called_once_with(connection)
            raise RuntimeError("dummy failure")
    assert connect.return_value.__exit__.call_args.args[0] is RuntimeError


def test_cli_does_not_expose_external_exception(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "ingest_pdf.py", "--pdf", "dummy.pdf", "--subject", "OS", "--module", "2", "--title", "Memory"
    ])
    monkeypatch.setattr(cli, "ingest_pdf", MagicMock(side_effect=RuntimeError("dummy-secret")))
    assert cli.main() == 1
    output = capsys.readouterr()
    assert "FAIL ingestion" in output.err
    assert "dummy-secret" not in output.out + output.err


def test_byte_loader_preserves_original_page_numbers(monkeypatch):
    texts = ["A full explanation of paging from the lecture.", "", "A full explanation of page tables."]
    reader = SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda text=text: text) for text in texts
    ])
    monkeypatch.setattr(pdf_loader, "PdfReader", lambda stream: reader)
    pages, skipped = pdf_loader.load_pdf_pages(b"dummy PDF bytes")
    assert [page["page"] for page in pages] == [1, 3]
    assert skipped == 1


def test_existing_document_ingestion_reuses_row_and_marks_ready(ingestion):
    ingestion.cursor.fetchone.side_effect = [(1, 2), (ingestion.document_id,)]
    result = pipeline.ingest_pdf(
        b"dummy PDF bytes", "OS", 2, "Memory", document_id=ingestion.document_id
    )
    assert result == ingestion.document_id
    calls = ingestion.cursor.execute.call_args_list
    assert not any("insert into documents" in call.args[0] for call in calls)
    assert calls[1].args[1] == (result, 1, 2, "official")
    assert "status = 'processing'" in calls[1].args[0]
    assert "status = 'ready'" in calls[-1].args[0]
    assert calls[-1].args[1] == (2, result)
    assert ingestion.cursor.executemany.call_args.args[1][0][0] == result
    ingestion.context.return_value.__exit__.assert_called_once_with(None, None, None)


def test_existing_document_scope_mismatch_prevents_chunk_writes(ingestion):
    ingestion.cursor.fetchone.side_effect = [(1, 2), None]
    with pytest.raises(pipeline.IngestError, match="Processing document not found"):
        pipeline.ingest_pdf(
            b"dummy PDF bytes", "OS", 2, "Memory", document_id=ingestion.document_id
        )
    ingestion.cursor.executemany.assert_not_called()


def test_existing_document_chunk_failure_rolls_back_without_ready(ingestion):
    ingestion.cursor.fetchone.side_effect = [(1, 2), (ingestion.document_id,)]
    ingestion.cursor.executemany.side_effect = RuntimeError("dummy failure")
    with pytest.raises(RuntimeError):
        pipeline.ingest_pdf(
            b"dummy PDF bytes", "OS", 2, "Memory", document_id=ingestion.document_id
        )
    assert ingestion.context.return_value.__exit__.call_args.args[0] is RuntimeError
    assert not any(
        "status = 'ready'" in call.args[0]
        for call in ingestion.cursor.execute.call_args_list
    )


def test_cli_keeps_path_based_ingestion(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "ingest_pdf.py", "--pdf", "dummy.pdf", "--subject", "OS",
        "--module", "2", "--title", "Memory", "--replace",
    ])
    ingest = MagicMock(return_value="dummy-document-id")
    monkeypatch.setattr(cli, "ingest_pdf", ingest)
    assert cli.main() == 0
    assert str(ingest.call_args.args[0]) == "dummy.pdf"
    assert ingest.call_args.args[1:] == ("OS", 2, "Memory")
    assert ingest.call_args.kwargs == {"replace": True}
    assert "PASS ingestion" in capsys.readouterr().out
