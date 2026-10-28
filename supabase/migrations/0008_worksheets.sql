/*
Store private student worksheets and their extracted questions.
A worksheet belongs to a single authenticated student.
The selected subject scopes all subsequent retrieval.
The uploaded file is sent to Gemini for extraction.
Questions are stored before any answers are generated.
Each question receives a separate answer request.
Question order follows the original extraction.
Unknown metadata is left null.
The module number is an extracted label.
Year is stored only when it appears in the worksheet.
Marks are stored only when they are shown.
The question number can contain letters or punctuation.
Question text includes answer choices for MCQs.
Question type is a constrained classification.
Answers retain their citation metadata.
Statuses support incremental progress and retry.
The backend handles all database writes.
RLS limits direct reads to the owner.
The service role bypasses RLS.
The backend must also filter by owner.
Worksheet deletion cascades to its questions.
Subject deletion cascades to worksheets.
The upload is not stored in a public bucket.
Question and answer data remain in Postgres.
The application must not log their text.
No API keys are stored in these tables.
A queue worker can process one question at a time.
A failed question does not delete other answers.
Answers are independent of other worksheet questions.
Only official subject documents provide evidence.
Existing Ask modes remain available.
Search model selection is shared with Ask.
The quiz remains a future feature.
Apply this migration through the SQL editor.
Run backend tests without real credentials.
*/
begin;
create table public.worksheets (
    id uuid primary key,
    owner_id uuid not null references public.profiles(id) on delete cascade,
    subject_id integer not null references public.subjects(id) on delete cascade,
    mode text not null check (mode in ('normal', 'strict')),
    status text not null check (status in ('extracting', 'answering', 'ready', 'failed')),
    error text,
    created_at timestamptz not null default now()
);
create table public.worksheet_questions (
    id bigserial primary key,
    worksheet_id uuid not null references public.worksheets(id) on delete cascade,
    position integer not null,
    module_number integer,
    year integer,
    question_number text,
    marks numeric,
    question_type text check (question_type in ('mcq','short','long','numerical')),
    question_text text not null,
    status text not null default 'queued' check (status in ('queued','answering','ready','failed')),
    answer text,
    sources jsonb,
    error text,
    unique (worksheet_id, position)
);
create index worksheet_owner_subject_idx on public.worksheets (owner_id, subject_id, created_at desc);
create index worksheet_questions_order_idx on public.worksheet_questions (worksheet_id, position);
alter table public.worksheets enable row level security;
alter table public.worksheet_questions enable row level security;
revoke all on public.worksheets, public.worksheet_questions from anon, authenticated;
grant select on public.worksheets, public.worksheet_questions to authenticated;
create policy "worksheet owner read" on public.worksheets for select to authenticated using (owner_id = auth.uid());
create policy "question owner read" on public.worksheet_questions for select to authenticated using (exists (select 1 from public.worksheets w where w.id = worksheet_id and w.owner_id = auth.uid()));
commit;
