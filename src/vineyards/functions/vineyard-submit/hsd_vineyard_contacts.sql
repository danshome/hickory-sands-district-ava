-- The vineyard form's one table: the sender's contact, kept privately, keyed
-- by the public issue's number (src/vineyards/functions/vineyard-submit/).
-- Dan runs this once in the Supabase project "Hickory Sands District AVA"
-- (ref yayebhncbagmebwgmezd): SQL Editor > New query > paste > Run
-- (src/vineyards/SETUP.md). It makes only objects named hsd_vineyard_*, so
-- vote-api's tables, functions and storage are untouched. Running it again
-- changes nothing that is already there.
--
-- Like vote-api's tables: row level security on (and forced) with no
-- policies, and every grant to the public (anon) and signed-in
-- (authenticated) roles revoked, so neither can read or write a row; only
-- the function, with the service role, touches it. No raw IP address is kept:
-- ip_hash is an HMAC of it with the function's secret IP_SALT, for the
-- limits only. closed_at is set by the function when the issue is closed
-- (the GitHub App's webhook) and cleared when it is reopened; the function
-- deletes a row a year after its issue was closed. Dan reads the table in the
-- dashboard's Table Editor.
create table if not exists public.hsd_vineyard_contacts (
  id             uuid primary key default gen_random_uuid(),
  submission_id  uuid not null unique,     -- made by the page; a retry is the same submission
  issue_number   integer unique,           -- set once the issue exists
  created_at     timestamptz not null default now(),
  closed_at      timestamptz,              -- when the issue was closed; null while it is open
  ip_hash        text not null check (char_length(ip_hash) = 32),
  contact_name   text not null check (char_length(contact_name) between 1 and 80),
  email          text check (email is null or char_length(email) between 3 and 120),
  phone          text check (phone is null or char_length(phone) between 10 and 30),
  constraint hsd_vineyard_contacts_reach check (email is not null or phone is not null)
);

-- (a table made before closed_at was added gets it here)
alter table public.hsd_vineyard_contacts add column if not exists closed_at timestamptz;
alter table public.hsd_vineyard_contacts enable row level security;
alter table public.hsd_vineyard_contacts force row level security;
revoke all on table public.hsd_vineyard_contacts from public, anon, authenticated;
-- no policies: nothing for anon or authenticated, by design

create index if not exists hsd_vineyard_contacts_limits
  on public.hsd_vineyard_contacts (ip_hash, created_at);
create index if not exists hsd_vineyard_contacts_closed
  on public.hsd_vineyard_contacts (closed_at) where closed_at is not null;

-- One transaction for each send, under one lock, so parallel sends cannot
-- slip past the limits: 'again' (this submission was seen: its row and issue
-- number, if any), else 'limit-ip' or 'limit-day', else 'new' with the new
-- row.
create or replace function public.hsd_vineyard_reserve(
  p_submission uuid, p_ip_hash text, p_name text, p_email text, p_phone text,
  p_per_ip integer, p_per_day integer)
returns table (id uuid, issue_number integer, verdict text)
language plpgsql security definer set search_path = public as $$
begin
  perform pg_advisory_xact_lock(hashtext('hsd_vineyard_contacts'));
  return query select c.id, c.issue_number, 'again'::text
    from hsd_vineyard_contacts c where c.submission_id = p_submission;
  if found then return; end if;
  if (select count(*) from hsd_vineyard_contacts c
      where c.ip_hash = p_ip_hash and c.created_at > now() - interval '1 day') >= p_per_ip then
    return query select null::uuid, null::integer, 'limit-ip'::text; return;
  end if;
  if (select count(*) from hsd_vineyard_contacts c
      where c.created_at > now() - interval '1 day') >= p_per_day then
    return query select null::uuid, null::integer, 'limit-day'::text; return;
  end if;
  return query insert into hsd_vineyard_contacts as c (submission_id, ip_hash, contact_name, email, phone)
    values (p_submission, p_ip_hash, p_name, p_email, p_phone)
    returning c.id, c.issue_number, 'new'::text;
end $$;
revoke all on function public.hsd_vineyard_reserve(uuid, text, text, text, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.hsd_vineyard_reserve(uuid, text, text, text, text, integer, integer)
  to service_role;
