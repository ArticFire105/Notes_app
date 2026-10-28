/*
Store private handwritten notes separately from official documents.
Each row belongs to exactly one signed-in user.
A user can keep one note for each subject.
The database unique constraint enforces that limit.
The backend controls processing and storage writes.
Students can read only their own metadata through RLS.
Chunk rows carry the owner for independent RLS checks.
Each chunk belongs to one parent note.
Composite foreign keys keep owner and subject consistent.
Deleting a note deletes its searchable chunks.
Embeddings contain text, never image bytes.
The private bucket stores original uploaded files.
Object names begin with the authenticated user ID.
Storage policies deny access to other users.
The backend still checks ownership on every request.
The service role is never sent to the browser.
Signed URLs are short lived.
No policy grants public file access.
Official documents keep their existing policies.
Notes and chunks are not shared between students.
Subject scope is required for every note.
Pages preserve their original page numbers.
Source labels identify personal notes in answers.
Replacement creates a new object before publishing it.
The application removes superseded objects after commit.
A failed OCR does not replace a working note.
The migration is applied in Supabase SQL Editor.
Run this after the profile and vector migrations.
No real credentials belong in this file.
The backend database role bypasses RLS.
Explicit backend filters are therefore mandatory.
RLS provides defense in depth for direct access.
The embedding model name prevents mixed vector spaces.
The unique index supports the per-subject limit.
No changes are made to official answer cache rows.
*/
begin;
create table public.personal_notes (
    id uuid primary key,
    user_id uuid not null references public.profiles(id) on delete cascade,
    subject_id int not null references public.subjects(id),
    title text not null,
    storage_path text not null,
    file_type text not null check (file_type in ('pdf','image')),
    created_at timestamptz not null default now(),
    unique (user_id, subject_id),
    unique (id, user_id, subject_id)
);
create table public.personal_note_chunks (
    id bigserial primary key,
    note_id uuid not null,
    user_id uuid not null,
    subject_id int not null,
    page int not null,
    chunk_index int not null,
    content text not null,
    embedding vector(768) not null,
    embedding_model text not null,
    foreign key (note_id, user_id, subject_id)
        references public.personal_notes(id, user_id, subject_id) on delete cascade
);
create index on public.personal_note_chunks (user_id, subject_id);
alter table public.personal_notes enable row level security;
alter table public.personal_note_chunks enable row level security;
revoke all on public.personal_notes, public.personal_note_chunks from anon, authenticated;
grant select on public.personal_notes, public.personal_note_chunks to authenticated;
create policy "read own note" on public.personal_notes for select to authenticated
    using ((select auth.uid()) = user_id);
create policy "read own note chunks" on public.personal_note_chunks for select to authenticated
    using ((select auth.uid()) = user_id);
insert into storage.buckets (id, name, public) values ('personal-notes', 'personal-notes', false)
    on conflict (id) do update set public = false;
create policy "read own personal files" on storage.objects for select to authenticated
    using (bucket_id = 'personal-notes' and (storage.foldername(name))[1] = (select auth.uid())::text);
commit;
