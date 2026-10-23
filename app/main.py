"""
Create the local FastAPI application and mount its routers.
The lifespan loads the cached embedder before serving requests.
A fixed failure response prevents exception details leaking.
Route functions keep blocking work in FastAPI worker threads.

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

# Do not deploy before Phase 4.
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.embeddings import get_embedder
from app.routers import ask, documents, subjects


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup warming avoids loading the same expensive model per request.
        get_embedder()
    except Exception:
        raise RuntimeError("Embedding model startup failed; check local setup.") from None
    yield


app = FastAPI(title="Lecture Notes API", lifespan=lifespan)


@app.middleware("http")
async def safe_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Catch before the server can log a traceback with driver credentials.
        return JSONResponse(status_code=500, content={"detail": "Request failed; check backend setup."})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(subjects.router)
app.include_router(documents.router)
app.include_router(ask.router)

