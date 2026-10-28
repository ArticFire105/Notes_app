/*
Record missing OCR pages for each private note.
This migration extends the personal notes table.
The OCR service reads pages before indexing.
Some pages can fail while others succeed.
The database retains their original page numbers.
The notes list returns them to the owner.
The interface can then show incomplete notes.
This warning survives a browser refresh.
Existing notes default to an empty list.
No transcription text is stored in this column.
The existing row security policy still applies.
The application writes the page numbers.
The browser cannot choose another note owner.
The original private file remains in storage.
Page numbers match the original upload.
Good pages remain searchable as chunks.
Failed pages do not produce chunks.
A replacement still uses a transaction.
A failed replacement preserves the old note.
OCR provider errors stay in backend logs.
Logs must not contain note content.
Logs must not contain provider credentials.
This field contains integers only.
The empty array means no known failures.
Apply this migration before running the updated app.
The migration does not alter existing chunks.
The migration does not change storage objects.
The column cannot be null.
The default also covers older application writes.
Students should review OCR against the original.
An empty page can also need manual review.
This change adds no external dependency.
Use the Supabase SQL editor to apply it.
The API and web app use the same field name.
Tests mock OCR and database access.
*/
create table if not exists public.course_figures (
    id uuid primary key,
    document_id uuid not null references public.documents(id) on delete cascade,
    page int not null,
    image_data bytea not null,
    content_type text not null default 'image/jpeg'
);
alter table public.course_figures enable row level security;
revoke all on public.course_figures from anon, authenticated;
alter table public.chunks add column if not exists figure_id uuid references public.course_figures(id) on delete cascade;
alter table public.personal_notes add column if not exists failed_pages integer[] not null default '{}';
