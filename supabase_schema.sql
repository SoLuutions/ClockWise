-- ==============================================================================
-- ClockWise - Secure Supabase Database Schema & Server-Side RPC Verifier
-- ==============================================================================
-- Run this entire script in your Supabase SQL Editor:
-- Dashboard (https://supabase.com/dashboard) -> SQL Editor -> New Query -> Paste & Run

-- 1. Enable extensions
create extension if not exists pgcrypto with schema extensions;

-- 2. Create the subscribers / users table
create table if not exists public.clockwise_users (
    id uuid default gen_random_uuid() primary key,
    email text unique not null,
    password text not null,                               -- Plain text or SHA-256 hex
    last_payment_date date not null default current_date,  -- YYYY-MM-DD
    is_active boolean not null default true,              -- Admin active switch
    full_name text default '',
    notes text default '',
    created_at timestamptz default now()
);

-- Index for fast lookups
create index if not exists idx_clockwise_users_email on public.clockwise_users(lower(email));

-- ==============================================================================
-- 3. Row Level Security (RLS) Configuration
-- ==============================================================================
alter table public.clockwise_users enable row level security;

-- Drop previous policies if re-running
drop policy if exists "Allow desktop app client lookup" on public.clockwise_users;
drop policy if exists "Deny public select" on public.clockwise_users;

-- Allow anonymous desktop client lookup (fallback query)
create policy "Allow desktop app client lookup"
on public.clockwise_users
for select
to anon
using (true);

-- ==============================================================================
-- 4. SECURE SERVER-SIDE RPC FUNCTION: verify_subscription
-- ==============================================================================
-- The desktop app calls this function to verify credentials and check the 30-day rule.
-- Uses PostgreSQL's built-in sha256() function to support both plain text & hashed passwords.

create or replace function public.verify_subscription(
    p_email text,
    p_password text
)
returns json
language plpgsql
security definer -- Runs with elevated database privileges inside Postgres
set search_path = public, extensions
as $$
declare
    v_user record;
    v_days_elapsed int;
    v_days_remaining int;
    v_max_days constant int := 30;
    v_hash text;
begin
    -- 1. Find user by case-insensitive email
    select * into v_user
    from public.clockwise_users
    where lower(email) = lower(trim(p_email));

    if not found then
        return json_build_object(
            'success', false,
            'error_code', 'NOT_FOUND',
            'message', 'Account not found. Please verify your email or contact support.'
        );
    end if;

    -- Compute SHA-256 hash using PostgreSQL built-in sha256() function
    v_hash := encode(sha256(convert_to(p_password, 'UTF8')), 'hex');

    -- 2. Verify password (supports plain text or SHA-256 hex hash)
    if v_user.password <> p_password and v_user.password <> v_hash then
        return json_build_object(
            'success', false,
            'error_code', 'INVALID_PASSWORD',
            'message', 'Incorrect password. Please try again.'
        );
    end if;

    -- 3. Check active status
    if not v_user.is_active then
        return json_build_object(
            'success', false,
            'error_code', 'DEACTIVATED',
            'message', 'Account has been deactivated. Please contact support.'
        );
    end if;

    -- 4. Calculate 30-day payment rule on the server
    v_days_elapsed := current_date - v_user.last_payment_date;
    
    if v_days_elapsed > v_max_days then
        return json_build_object(
            'success', false,
            'error_code', 'EXPIRED',
            'days_elapsed', v_days_elapsed,
            'days_remaining', 0,
            'last_payment_date', v_user.last_payment_date,
            'message', format('Subscription expired: Last payment was on %s (%s days ago - limit is 30 days). Access is restricted until renewed.', to_char(v_user.last_payment_date, 'Mon DD, YYYY'), v_days_elapsed)
        );
    end if;

    v_days_remaining := greatest(0, v_max_days - greatest(0, v_days_elapsed));

    return json_build_object(
        'success', true,
        'error_code', null,
        'email', v_user.email,
        'full_name', v_user.full_name,
        'days_remaining', v_days_remaining,
        'last_payment_date', v_user.last_payment_date,
        'message', format('Subscription active: %s day%s remaining.', v_days_remaining, case when v_days_remaining = 1 then '' else 's' end)
    );
end;
$$;

-- Grant execution permission to anonymous and authenticated client roles
grant execute on function public.verify_subscription(text, text) to anon;
grant execute on function public.verify_subscription(text, text) to authenticated;

-- ==============================================================================
-- 5. Active User Accounts (Safe to run or edit)
-- ==============================================================================

-- Account 1: Clark Lindley Suan (Your Personal Account)
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'vynchsuan@gmail.com',
    'pass123',
    current_date,
    true,
    'Clark Lindley Suan',
    'Owner / Admin Account'
)
on conflict (email) do update
set last_payment_date = current_date, is_active = true, password = 'pass123';

-- Account 2: App Email Account
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'clark@clockwise.app',
    'pass123',
    current_date,
    true,
    'Clark Lindley',
    'Active subscriber'
)
on conflict (email) do update
set last_payment_date = current_date, is_active = true, password = 'pass123';

-- Account 3: Domain Email Account
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'clark@clarklindleysuan.com',
    'pass123',
    current_date,
    true,
    'Clark Lindley Suan',
    'Personal domain account'
)
on conflict (email) do update
set last_payment_date = current_date, is_active = true, password = 'pass123';

-- Account 4: Expired subscriber test (> 30 days old)
insert into public.clockwise_users (email, password, last_payment_date, is_active, full_name, notes)
values (
    'expired@clockwise.app',
    'pass123',
    current_date - interval '45 days',
    true,
    'Expired Customer',
    'Needs renewal'
)
on conflict (email) do update
set last_payment_date = current_date - interval '45 days', is_active = true;
