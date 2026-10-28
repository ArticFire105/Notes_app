/*
Store extracted lecture figures beside their text descriptions.
This migration runs after the initial schema.
Figures belong to official documents.
Deleting a document deletes its figures.
Each figure retains its original page or slide number.
Image bytes are stored privately in Postgres.
The backend serves images only to signed-in students.
A chunk can point to its corresponding figure.
Text-only chunks keep a null figure ID.
Captions become ordinary searchable text chunks.
Only captions are sent to the embedding model.
Actual image bytes are never embedded.
The original document remains in Storage.
A figure is extracted only during ingestion.
Existing documents must be reprocessed or re-uploaded.
Foreign keys keep figure ownership consistent.
RLS denies anonymous access to image rows.
The trusted backend checks source type itself.
There is no client write policy for images.
The service role key stays on the backend.
Old cached answers are invalidated on ingestion.
New rows are published with chunks in one transaction.
Failed image processing does not publish a partial document.
The user runs this in Supabase SQL Editor.
No credentials belong in this migration.
Image size can affect database storage usage.
The app downsizes extracted images before storage.
Small decorative images are skipped.
Raster images include PNG and JPEG input.
Vector shapes may not be extractable as raster images.
Slide and page numbers remain stable.
The answer identifies the corresponding image.
Private student notes use separate tables.
Students cannot upload official images.
Run the backend tests with uv run pytest.
*/
begin;
create table public.course_figures (
    id uuid primary key,
    document_id uuid not null references public.documents(id) on delete cascade,
    page int not null,
    image_data bytea not null,
    content_type text not null default 'image/jpeg'
);
alter table public.course_figures enable row level security;
revoke all on public.course_figures from anon, authenticated;
alter table public.chunks add column figure_id uuid references public.course_figures(id) on delete cascade;
commit;
