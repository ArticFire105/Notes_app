-- Give the department its five subject scopes before uploading any notes.
-- Five placeholder modules per subject make the initial selection usable.
-- Conflict handling lets you rerun this without losing renamed module titles.

begin;

insert into subjects (code, name) values
  ('OS', 'Operating Systems'),
  ('SE', 'Software Engineering'),
  ('POC', 'Principles of Cryptography'),
  ('CN', 'Computer Networks'),
  ('EOM', 'Essentials of Management')
on conflict (code) do nothing;

-- Resolve IDs by code instead of assuming serial IDs start at a particular value.
insert into modules (subject_id, number, title)
select subjects.id, module_number, 'Module ' || module_number
from subjects
cross join generate_series(1, 5) as module_numbers(module_number)
where subjects.code in ('OS', 'SE', 'POC', 'CN', 'EOM')
on conflict (subject_id, number) do nothing;

commit;
