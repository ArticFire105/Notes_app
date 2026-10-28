"""Keep background work visible across backend revisions.
The database is the source of truth for heartbeat timestamps.
Each process tracks the work that it has scheduled.
The maintenance thread periodically refreshes those rows.
It also checks for jobs whose heartbeat has gone stale.
Official documents may wait in an in-process queue.
Those queued documents need heartbeats too.
Worksheet extraction uses a background task.
Worksheet answering also uses a background task.
The tracked worksheet covers its queued questions.
Reference counts support overlapping jobs in one process.
The database provides a shared clock between revisions.
No student text is included in heartbeat records.
No tokens or credentials are logged.
The maintenance loop starts with the FastAPI lifespan.
It stops when that lifespan closes.
Tests can call each maintenance step independently.
Database errors are reported without provider diagnostics.
The next cycle retries a failed heartbeat.
Recovery uses a grace period longer than the interval.
Rows are touched only while they remain processing.
Completed records do not need a heartbeat.
Failed records can be retried by their owner.
An interrupted extraction must be uploaded again.
The original official upload stays in Storage.
Queued questions can be retried from the worksheet.
The helper does not store background job payloads.
The helper does not implement a durable job queue.
The process still holds its current work in memory.
The migration creates the timestamp columns.
Apply that migration before starting this backend.
Scale-to-zero still interrupts in-process work.
The next running replica can detect stale records.
No third-party dependency is added.
Run uv run pytest for offline tests.
"""

from threading import Lock

from app.db import get_conn

_lock = Lock()
_active = {"document": {}, "worksheet": {}}


def register(kind, item_id):
    with _lock:
        jobs = _active[kind]
        jobs[item_id] = jobs.get(item_id, 0) + 1


def unregister(kind, item_id):
    with _lock:
        jobs = _active[kind]
        count = jobs.get(item_id, 0)
        if count <= 1:
            jobs.pop(item_id, None)
        else:
            jobs[item_id] = count - 1


def refresh():
    with _lock:
        documents = list(_active["document"])
        worksheets = list(_active["worksheet"])
    if not documents and not worksheets:
        return
    with get_conn() as connection:
        with connection.cursor() as cursor:
            if documents:
                cursor.execute("update documents set job_heartbeat_at=now() where id=any(%s) and status='processing'", (documents,))
            if worksheets:
                cursor.execute("update worksheets set job_heartbeat_at=now() where id=any(%s)", (worksheets,))
                cursor.execute("update worksheet_questions set job_heartbeat_at=now() where worksheet_id=any(%s) and status in ('queued','answering')", (worksheets,))
