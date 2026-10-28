/*
Create the Phase 5 usage ledger and shared official-answer cache.
Run this after 0003_profiles_roles.sql in the Supabase SQL Editor.
The backend makes all writes through its trusted connection.
Each user has one usage row per Dubai calendar day.
The composite primary key supports atomic allowance increments.
Requests reserve server-key calls before generation begins.
Reservations also count calls whose provider outcome is uncertain.
Empty retrieval reservations are returned by the backend.
Input and output counts come from model usage metadata.
Costs are estimates using prices configured by the operator.
Unknown pricing is displayed as unknown by the API.
Zero in the cost column is not proof of zero billed spend.
The daily global cap sums request reservations.
The backend serializes global checks with an advisory lock.
This lock works across backend processes sharing the database.
The budget compares recorded completed-call estimates.
In-flight requests can overshoot the estimated daily budget.
The answer cache stores only grounded successful responses.
Not-found answers are never inserted.
Provider errors are never inserted.
Cache keys include normalized questions and the requested scope.
The ready official document set versions cached answers.
New ingestion also deletes this subject's cached responses.
Sources are stored as JSON beside their answer.
Cache hits increment a counter without consuming questions.
Cache results are served only through authenticated API routes.
BYOK secrets are never stored in either table.
Access tokens are never stored in either table.
Both tables have row level security enabled.
Authenticated users can read only their own usage.
Direct clients cannot mutate usage rows.
Direct clients cannot read or write the shared cache.
Database-owner backend connections remain trusted.
Apply this migration yourself; tests do not connect to Supabase.
*/

begin;

create table public.usage_daily (
    user_id uuid not null references public.profiles(id) on delete cascade,
    day date not null,
    requests int not null default 0 check (requests >= 0),
    input_tokens int not null default 0 check (input_tokens >= 0),
    output_tokens int not null default 0 check (output_tokens >= 0),
    est_cost_usd numeric(10,6) not null default 0 check (est_cost_usd >= 0),
    primary key (user_id, day)
);

-- Global totals filter by day rather than the composite key's user prefix.
create index usage_daily_day_idx on public.usage_daily (day);

create table public.answer_cache (
    id bigserial primary key,
    cache_key text unique not null,
    subject_id int not null references public.subjects(id) on delete cascade,
    module_id int references public.modules(id) on delete cascade,
    document_id uuid references public.documents(id) on delete cascade,
    answer text not null,
    sources jsonb not null,
    hits int not null default 0 check (hits >= 0),
    created_at timestamptz not null default now()
);

create index answer_cache_subject_idx on public.answer_cache (subject_id);

alter table public.usage_daily enable row level security;
alter table public.answer_cache enable row level security;

revoke all on public.usage_daily, public.answer_cache from anon, authenticated;
revoke all on sequence public.answer_cache_id_seq from anon, authenticated;
grant select on public.usage_daily to authenticated;

create policy usage_daily_read_own on public.usage_daily
    for select to authenticated using ((select auth.uid()) = user_id);

commit;

