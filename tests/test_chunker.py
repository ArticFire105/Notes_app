"""Check citation boundaries before any embedding or database work runs.
Use plain text pages so these tests require no PDFs, model, or connection.
Exercise long and empty pages to protect chunk size and ordering.
"""

from app.ingest.chunker import CHUNK_SIZE, chunk_pages


def test_chunks_keep_page_numbers_and_do_not_mix_pages():
    pages = [
        {"page": 2, "text": "memory paging " * 250},
        {"page": 7, "text": "network routing " * 250},
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) > 2
    assert {chunk["page"] for chunk in chunks} == {2, 7}
    for chunk in chunks:
        if chunk["page"] == 2:
            assert "routing" not in chunk["content"]
        else:
            assert "paging" not in chunk["content"]
        assert len(chunk["content"]) <= CHUNK_SIZE
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))


def test_empty_and_whitespace_pages_make_no_empty_chunks():
    chunks = chunk_pages([
        {"page": 1, "text": ""},
        {"page": 2, "text": " \n\t "},
        {"page": 3, "text": "A useful paragraph about memory management."},
    ])
    assert chunks == [{
        "page": 3, "chunk_index": 0,
        "content": "A useful paragraph about memory management.",
    }]
    assert chunk_pages([]) == []


def test_long_unbroken_text_is_split_without_exceeding_chunk_size():
    chunks = chunk_pages([{"page": 4, "text": "x" * 2500}])
    assert len(chunks) > 1
    assert all(chunk["content"] and chunk["page"] == 4 for chunk in chunks)
    assert all(len(chunk["content"]) <= CHUNK_SIZE for chunk in chunks)
