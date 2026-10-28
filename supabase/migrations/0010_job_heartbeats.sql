/*
Track background work across backend restarts.
The backend updates these timestamps while work is active.
Startup recovery checks timestamps before marking work failed.
A periodic recovery check handles jobs that become stale later.
Documents keep their source files in Supabase Storage.
Worksheet questions and answers remain in Postgres.
The heartbeat never contains document or question text.
It never contains an API key.
It uses the database clock rather than the container clock.
The database clock is shared across revisions.
Five minutes without a heartbeat indicates interrupted work.
Long tasks need heartbeats even when they make no progress.
Queued document uploads also need heartbeats.
Worksheet extraction needs a heartbeat.
Worksheet answer jobs need a heartbeat.
Question retry jobs need a heartbeat.
Each timestamp belongs to the corresponding database row.
New rows start with the database's current time.
Existing rows get a timestamp when this migration is applied.
Old interrupted jobs become eligible after the grace period.
Ready records are ignored by recovery.
Failed records remain available for retry.
The backend must still enforce ownership.
The timestamp does not grant permissions.
No extra database extension is required.
No new application dependency is required.
The migration runs before the new backend is deployed.
Apply it in the Supabase SQL Editor.
Apply earlier project migrations first.
Back up production data before schema changes.
This operation does not remove existing content.
The container filesystem remains temporary.
The Azure app can scale down to zero.
Tests use synthetic data and no real secrets.
Run uv run pytest after application changes.
*/
begin;
alter table public.documents add column job_heartbeat_at timestamptz not null default now();
alter table public.worksheets add column job_heartbeat_at timestamptz not null default now();
alter table public.worksheet_questions add column job_heartbeat_at timestamptz not null default now();
commit;
