-- DataRopes Recruitment Tool: authentication users and audit trail.
-- Service-role bypass only; no anon/authenticated policies grant access.

CREATE TYPE public.user_role AS ENUM (
    'hr',
    'interviewer',
    'ceo'
);

CREATE TABLE public.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL CHECK (length(btrim(email)) > 0),
    password_hash text NOT NULL CHECK (length(btrim(password_hash)) > 0),
    full_name text NOT NULL CHECK (length(btrim(full_name)) > 0),
    role public.user_role NOT NULL DEFAULT 'hr',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Email identity lookup is case-insensitive.
CREATE UNIQUE INDEX users_email_lower_unique_idx
    ON public.users (lower(email));

CREATE INDEX users_role_idx
    ON public.users (role)
    WHERE is_active;

CREATE TABLE public.audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
    actor_email text,
    action text NOT NULL CHECK (length(btrim(action)) > 0),
    entity text NOT NULL CHECK (length(btrim(entity)) > 0),
    entity_id text,
    timestamp timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX audit_logs_actor_timestamp_idx
    ON public.audit_logs (actor_id, timestamp DESC);

CREATE INDEX audit_logs_action_timestamp_idx
    ON public.audit_logs (action, timestamp DESC);

CREATE INDEX audit_logs_entity_idx
    ON public.audit_logs (entity, entity_id);

-- Backend access goes through the Supabase service-role client only.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_service_role_all
    ON public.users
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY audit_logs_service_role_all
    ON public.audit_logs
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
