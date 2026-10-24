/*
Create application profiles for Supabase users.
This migration implements Phase 4.
Run it after the Phase 0 migration.
Run it manually in the Supabase SQL Editor.

Auth owns the login identity.
Profiles hold application roles.
Every new profile starts as a student.
User metadata cannot choose a role.

The signup trigger runs with trusted privileges.
Its search path is deliberately empty.
Table references are explicitly qualified.
Existing auth users are backfilled too.

Document uploads record their authenticated uploader.
Older documents may have no uploader.
Uploader IDs must refer to real profiles.
Deleting an uploader preserves official documents.

RLS protects direct client database access.
Authenticated users can read their own profile.
Clients cannot change profile roles.
Only trusted SQL can promote administrators.

Subjects and modules are read-only to clients.
Official documents and past papers are readable.
Student documents are not exposed by this policy.
Chunks retain their existing deny-by-default RLS.

The backend database connection bypasses RLS.
Backend authentication remains the primary check.
RLS provides a second lock for direct API access.
No Storage policies or later-phase tables are added.
The transaction rolls back if any migration statement fails.
*/

begin;

create table public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    full_name text,
    role text not null default 'student' check (role in ('student', 'rep', 'admin')),
    year int,
    school text,
    created_at timestamptz default now()
);

create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (id, email, full_name)
    values (new.id, new.email, new.raw_user_meta_data ->> 'full_name');
    return new;
end;
$$;

revoke execute on function public.handle_new_user() from public, anon, authenticated;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- Existing test accounts also need profiles before uploader IDs are constrained.
insert into public.profiles (id, email, full_name)
select id, email, raw_user_meta_data ->> 'full_name'
from auth.users;

alter table public.documents add constraint documents_uploaded_by_fkey
    foreign key (uploaded_by) references public.profiles(id) on delete set null;

alter table public.profiles enable row level security;
alter table public.subjects enable row level security;
alter table public.modules enable row level security;
alter table public.documents enable row level security;
alter table public.chunks enable row level security;

revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
revoke all on public.subjects, public.modules, public.documents from anon, authenticated;
grant select on public.subjects, public.modules, public.documents to authenticated;

create policy "users can read their own profile" on public.profiles
    for select to authenticated using ((select auth.uid()) = id);
create policy "authenticated users can read subjects" on public.subjects
    for select to authenticated using (true);
create policy "authenticated users can read modules" on public.modules
    for select to authenticated using (true);
create policy "authenticated users can read official documents" on public.documents
    for select to authenticated using (source_type in ('official', 'past_paper'));

-- Run after your first OTP login, replacing this placeholder yourself:
-- update public.profiles set role = 'admin' where email = 'YOUR_EMAIL@dxb.manipal.edu';

commit;
