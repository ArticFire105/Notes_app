/*
Store private worksheet conversation turns.
Each row belongs to one worksheet.
Worksheet deletion cascades to all turns.
Each turn stores one student message and one reply.
An optional question reference groups question follow-ups.
The question reference is nullable for worksheet-wide chat.
The foreign key clears that reference if a question is removed.
The message contains private student text.
The answer contains private assistant text.
Sources retain document and page citation metadata.
The backend verifies worksheet ownership before reading.
RLS also protects direct authenticated reads.
Anonymous users have no access.
The service role is restricted by backend checks.
Rows are returned in creation order.
The primary key breaks timestamp ties.
No keys are stored in this table.
No uploaded files are stored in this table.
No text should be written to logs.
Question deletion must not reveal other worksheets.
All writes go through the backend.
Students cannot write rows directly.
Students may read only their own worksheet turns.
The worksheet foreign key provides deletion cleanup.
The question foreign key is optional.
The subject is resolved through the worksheet.
Saved citations are checked against current course documents.
Answers are generated from the current subject scope.
Conversation history is limited before model requests.
Retrieval uses question text and the latest message.
A follow-up can reference a saved answer.
The model must distinguish evidence from instructions.
The project runs this migration through Supabase.
No new dependency is needed.
Run the backend tests with uv run pytest.
*/
begin;
create table public.worksheet_chat (
    id bigserial primary key,
    worksheet_id uuid not null references public.worksheets(id) on delete cascade,
    question_id bigint references public.worksheet_questions(id) on delete set null,
    message text not null,
    answer text not null,
    sources jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);
create index worksheet_chat_order on public.worksheet_chat (worksheet_id, id);
alter table public.worksheet_chat enable row level security;
revoke all on public.worksheet_chat from anon, authenticated;
grant select on public.worksheet_chat to authenticated;
create policy "worksheet chat owner read" on public.worksheet_chat for select to authenticated
using (exists (select 1 from public.worksheets w where w.id = worksheet_id and w.owner_id = auth.uid()));
commit;
