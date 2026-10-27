-- ==============================================================================
-- ClockWise - Supabase Subscription & Authentication Database Schema
-- ==============================================================================
-- Run this script in your Supabase SQL Editor (Dashboard -> SQL Editor -> New Query)

-- 1. Create the subscribers / users table
create table if not exists public.clockwise_users (
    id uuid default gen_random_uuid() primary key,
    email text unique not null,
    password text not null,                      -- Plain text or SHA-256 hash (easy manual entry)
    last_payment_date date not null default current_date, -- YYYY-MM-DD
    is_active boolean not null default true,     -- Manual kill-switch
    full_name text default '',
    notes text default '',
    created_at timestamptz default now()
);

-- 2. Configure Row Level Security (RLS)
alter table public.clockwise_users enable row level security;

-- Drop previous policy if re-running
drop policy if exists "Allow desktop app client lookup" on public.clockwise_users;

-- Allow anon desktop app key to query user credentials & payment date
create policy "Allow desktop app client lookup"
on public.clockwise_users
for select
to anon
using (true);

-- 3. Optional: Helpful indexes
create index if not exists idx_clockwise_users_email on public.clockwise_users(email);

-- ==============================================================================
-- Sample Data for Testing (You can edit or run these directly in Supabase)
-- ==============================================================================

-- Account 1: Active subscriber (Paid today / within 30 days) -> ACCESS GRANTED
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'clark@clockwise.app',
    'pass123',
    current_date,
    true,
    'Clark Lindley',
    'Active trial user'
)
on conflict (email) do update
set last_payment_date = current_date, is_active = true;

-- Account 2: Expired subscriber (Paid 45 days ago) -> ACCESS RESTRICTED (> 30 days)
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'expired@clockwise.app',
    'pass123',
    current_date - interval '45 days',
    true,
    'Expired Customer',
    'Need to renew subscription'
)
on conflict (email) do update
set last_payment_date = current_date - interval '45 days', is_active = true;

-- Account 3: Deactivated subscriber -> ACCESS RESTRICTED
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'suspended@clockwise.app',
    'pass123',
    current_date,
    false,
    'Suspended Account',
    'Manually disabled by admin'
)
on conflict (email) do update
set is_active = false;
