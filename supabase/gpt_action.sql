create table if not exists public.gpt_decision_requests (
    decision_id text primary key,
    captured_at timestamptz not null,
    source text not null default 'custom_gpt',
    matchup text,
    slate_date date,
    prompt text,
    request_json jsonb not null,
    response_json jsonb not null,
    validation_json jsonb not null,
    metadata_json jsonb not null default '{}'::jsonb
);

alter table public.gpt_decision_requests
    add column if not exists request_json jsonb;

alter table public.gpt_decision_requests
    add column if not exists response_json jsonb;

alter table public.gpt_decision_requests
    add column if not exists validation_json jsonb;

alter table public.gpt_decision_requests
    add column if not exists metadata_json jsonb not null default '{}'::jsonb;

update public.gpt_decision_requests
set
    request_json = coalesce(request_json, '{}'::jsonb),
    response_json = coalesce(response_json, '{}'::jsonb),
    validation_json = coalesce(validation_json, '{}'::jsonb)
where request_json is null
   or response_json is null
   or validation_json is null;

alter table public.gpt_decision_requests
    alter column request_json set not null,
    alter column response_json set not null,
    alter column validation_json set not null;

create table if not exists public.gpt_decision_legs (
    leg_id text primary key,
    decision_id text not null references public.gpt_decision_requests(decision_id) on delete cascade,
    rank integer not null,
    captured_at timestamptz not null,
    slate_date date,
    matchup text,
    selection_id text,
    prop_id text,
    fixture_slug text,
    player_name text,
    team_name text,
    market_key text,
    market_name text,
    side text,
    line numeric,
    odds numeric,
    playable boolean not null default false,
    status text,
    selection_json jsonb not null,
    decision_profile_json jsonb not null default '{}'::jsonb,
    risk_flags_json jsonb not null default '[]'::jsonb,
    settlement_status text not null default 'unsettled',
    actual_stat numeric,
    settled_at timestamptz,
    settlement_confidence numeric,
    settlement_source text
);

alter table public.gpt_decision_legs
    add column if not exists decision_profile_json jsonb not null default '{}'::jsonb;

alter table public.gpt_decision_legs
    add column if not exists risk_flags_json jsonb not null default '[]'::jsonb;

alter table public.gpt_decision_legs
    add column if not exists settlement_status text not null default 'unsettled';

alter table public.gpt_decision_legs
    add column if not exists actual_stat numeric;

alter table public.gpt_decision_legs
    add column if not exists settled_at timestamptz;

alter table public.gpt_decision_legs
    add column if not exists settlement_confidence numeric;

alter table public.gpt_decision_legs
    add column if not exists settlement_source text;

create table if not exists public.market_mappings (
    sport text not null default 'mlb',
    stake_display_name text not null,
    internal_market_key text not null,
    stat_key text,
    group_name text,
    last_seen_at timestamptz not null,
    active boolean not null default true,
    examples jsonb not null default '[]'::jsonb,
    primary key (sport, stake_display_name, internal_market_key)
);

create index if not exists gpt_decision_requests_slate_date_idx
    on public.gpt_decision_requests (slate_date);

create index if not exists gpt_decision_legs_slate_date_idx
    on public.gpt_decision_legs (slate_date);

create index if not exists gpt_decision_legs_market_idx
    on public.gpt_decision_legs (market_key, side);

create index if not exists market_mappings_active_idx
    on public.market_mappings (sport, active);

create table if not exists public.local_ui_jobs (
    job_id text primary key,
    job_type text not null,
    status text not null default 'pending',
    request_json jsonb not null,
    result_json jsonb,
    error_message text,
    worker_id text,
    created_at timestamptz not null default now(),
    claimed_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    expires_at timestamptz
);

alter table public.local_ui_jobs
    add column if not exists result_json jsonb;

alter table public.local_ui_jobs
    add column if not exists error_message text;

alter table public.local_ui_jobs
    add column if not exists worker_id text;

alter table public.local_ui_jobs
    add column if not exists claimed_at timestamptz;

alter table public.local_ui_jobs
    add column if not exists completed_at timestamptz;

alter table public.local_ui_jobs
    add column if not exists updated_at timestamptz not null default now();

alter table public.local_ui_jobs
    add column if not exists expires_at timestamptz;

create index if not exists local_ui_jobs_pending_idx
    on public.local_ui_jobs (job_type, status, created_at);

create index if not exists local_ui_jobs_expires_idx
    on public.local_ui_jobs (expires_at);

notify pgrst, 'reload schema';
