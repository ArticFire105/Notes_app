-- Phase 0 stores files and searchable text before any application features exist.
-- Run this once in the Supabase SQL Editor, then run seed.sql.
-- No client policies are granted until authentication is implemented later.

begin;

create extension if not exists vector;

-- Subjects provide the home-page labels and the top-level retrieval scope.
create table subjects (
  -- Stable IDs support relationships; codes keep the five subjects recognizable.
  id serial primary key,
  code text unique not null,
  name text not null
);

-- Modules let a student restrict questions to a particular part of a subject.
create table modules (
  -- Cascading removes a subject's module labels if that subject is removed.
  id serial primary key,
  subject_id int not null references subjects(id) on delete cascade,
  -- Numbers stay stable when placeholder titles are renamed.
  number int not null,
  title text not null,
  unique (subject_id, number)
);

-- Documents connect a raw uploaded file to its processing state and text chunks.
create table documents (
  -- A nullable module allows whole-subject documents such as past papers.
  id uuid primary key default gen_random_uuid(),
  subject_id int not null references subjects(id),
  module_id int references modules(id),
  source_type text not null check (source_type in ('official','student','past_paper')),
  -- File metadata supports citations and locating the original in Storage.
  title text not null,
  storage_path text,
  page_count int,
  exam_year int,
  -- State and error details will explain incomplete or failed ingestion.
  status text not null default 'ready',
  error text,
  -- The uploader relationship is deferred until profiles exist in Phase 4.
  uploaded_by uuid,
  created_at timestamptz default now()
);

-- Chunks are the searchable pieces; deleting a file removes its pieces too.
create table chunks (
  id bigserial primary key,
  document_id uuid not null references documents(id) on delete cascade,
  -- Copying scope fields avoids joins during filtered vector search.
  subject_id int not null,
  module_id int,
  source_type text not null,
  -- Page and order let later answers cite the original PDF precisely.
  page int not null,
  chunk_index int not null,
  content text not null,
  -- Model identity prevents comparing vectors from incompatible model spaces.
  embedding vector(768) not null,
  embedding_model text not null,
  created_at timestamptz default now()
);

-- The cosine operator class must match the later cosine-distance query.
create index on chunks using hnsw (embedding vector_cosine_ops);
-- Ordinary scope filtering also needs an index independent of vector search.
create index on chunks (subject_id, module_id, source_type);

-- Deny direct client access until policies exist. The backend must use a trusted
-- database role that bypasses RLS, such as the supplied postgres pooler role.
alter table subjects enable row level security;
alter table modules enable row level security;
alter table documents enable row level security;
alter table chunks enable row level security;

commit;
