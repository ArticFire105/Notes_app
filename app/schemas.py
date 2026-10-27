"""
Define the public request and response shapes.
Pydantic rejects invalid scopes before calling services.
Whitespace-only questions are rejected after trimming.
Only public document metadata is exposed.

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

Ask responses include the Phase 5 remaining daily allowance.
Run the API from the repository root.
Use uv run pytest for the offline test suite.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Subject(BaseModel):
    id: int
    code: str
    name: str


class Module(BaseModel):
    id: int
    subject_id: int
    number: int
    title: str


class DocumentOut(BaseModel):
    id: UUID
    title: str
    module: int | None
    page_count: int | None
    status: Literal["processing", "ready", "failed"]
    created_at: datetime
    error: str | None = None
    file_type: Literal["pdf", "pptx"] = "pdf"


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AskRequest(BaseModel):
    question: Question
    subject_id: int = Field(gt=0)
    module_id: int | None = Field(default=None, gt=0)
    document_id: UUID | None = None
    mode: Literal["normal", "strict"] = "normal"
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)


class Source(BaseModel):
    document_id: UUID | None = None
    n: int
    document: str
    module: int | None
    page: int
    score: float
    page_label: str | None = None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    usage: Usage
    remaining: int

