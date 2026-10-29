"""
Create the local FastAPI application and mount its routers.
The lifespan loads the cached embedder before serving requests.
A fixed failure response prevents exception details leaking.
Route functions keep blocking work in FastAPI worker threads.

This module combines the Phase 3 API and Phase 4 authentication.
The API wraps the existing ingestion and answering code.
Health and development-only documentation allow anonymous access.
Interactive API documentation is disabled unless APP_ENV=development.

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

Authentication and quotas are required; the frontend comes later.
Run the API from the repository root.
Use uv run pytest for the offline test suite.
"""

from contextlib import asynccontextmanager
import os
from threading import Event, Thread

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.embeddings import get_embedder
from app.auth import get_current_user
from app.db import get_conn
from app import heartbeats
from app.logging_safety import install_header_redaction
from app.routers import ask, documents, login, me, subjects, notes, worksheets


def recover_interrupted_jobs():
    # The queue and worksheet workers live only in the previous process.
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""update documents set status='failed', error=%s
                where source_type='official' and status='processing'
                and job_heartbeat_at < now() - interval '5 minutes'""",
                ("Processing was interrupted by a server restart. Please retry.",))
            cursor.execute("""update worksheet_questions set status='failed', error=%s
                where status in ('queued', 'answering')
                and job_heartbeat_at < now() - interval '5 minutes'""",
                ("Processing was interrupted by a server restart. Please retry.",))
            cursor.execute("""update worksheets set status='failed', error=%s
                where status in ('extracting', 'answering')
                and job_heartbeat_at < now() - interval '5 minutes'""",
                ("Processing was interrupted by a server restart. Retry a question, or upload the worksheet again.",))


def maintain_jobs(stop):
    while not stop.wait(30):
        try:
            heartbeats.refresh()
            recover_interrupted_jobs()
        except Exception:
            # Driver exceptions can contain connection credentials.
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup warming avoids loading the same expensive model per request.
        get_embedder()
        recover_interrupted_jobs()
    except Exception:
        raise RuntimeError("Backend startup failed; check backend configuration and database.") from None
    stop = Event()
    worker = Thread(target=maintain_jobs, args=(stop,), daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=1)


install_header_redaction()

async def safe_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Catch before the server can log a traceback with driver credentials.
        return JSONResponse(status_code=500, content={"detail": "Request failed; check backend setup."})


def health():
    return {"status": "ok"}


def create_app():
    # Read this non-secret process setting without loading credentials at import.
    # Explicit opt-in keeps documentation off on an unconfigured production host.
    development = os.getenv("APP_ENV", "production") == "development"
    application = FastAPI(
        title="Lecture Notes API", lifespan=lifespan,
        docs_url="/docs" if development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if development else None,
        swagger_ui_parameters={"persistAuthorization": False},
    )
    application.middleware("http")(safe_errors)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000" if development else "",
        ).split(",") if origin.strip() and origin.strip() != "*"],
        allow_credentials=True,
        max_age=86400,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-User-Api-Key", "X-Browser-Session"],
        expose_headers=["Retry-After"],
    )
    application.get("/health")(health)
    application.include_router(login.router)
    application.include_router(subjects.router, dependencies=[Depends(get_current_user)])
    application.include_router(documents.router, dependencies=[Depends(get_current_user)])
    application.include_router(ask.router, dependencies=[Depends(get_current_user)])
    application.include_router(me.router)
    application.include_router(notes.router)
    application.include_router(worksheets.router)
    return application


app = create_app()

