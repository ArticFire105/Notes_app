"""Split extracted pages into small text pieces for document embedding.
Split each page separately so chunks never cross citation page boundaries.
Keep a document-wide zero-based index to preserve chunk ordering.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter


CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_pages(pages: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = []
    for page in pages:
        for text in splitter.split_text(page["text"]):
            content = text.strip()
            if content:
                chunks.append({
                    "page": page["page"],
                    "chunk_index": len(chunks),
                    "content": content,
                })
    return chunks
