-- DataRopes Recruitment Tool: initial relational schema.
-- Apply this migration once to the Supabase project's public schema.

CREATE TYPE public.job_status AS ENUM (
    'draft',
    'posted',
    'closed'
);

CREATE TYPE public.application_stage AS ENUM (
    'sync_evaluation',
    'technical_interview',
    'ceo_review',
    'closed'
);

CREATE TYPE public.screening_decision AS ENUM (
    'pass',
    'fail'
);

CREATE TYPE public.pipeline_status AS ENUM (
    'failed_at_sync',
    'active_pipeline',
    'pending_ceo_decision',
    'closed_complete'
);

CREATE TYPE public.final_decision AS ENUM (
    'pending',
    'pass',
    'fail'
);

CREATE TYPE public.interview_status AS ENUM (
    'pending',
    'complete'
);

CREATE TABLE public.jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    tech_stack text NOT NULL,
    seniority text NOT NULL CHECK (length(btrim(seniority)) > 0),
    compensation_min numeric(12, 2),
    compensation_max numeric(12, 2),
    jd_markdown text,
    google_form_id text,
    google_form_url text,
    linkedin_blurb text,
    status public.job_status NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT jobs_compensation_min_nonnegative
        CHECK (compensation_min IS NULL OR compensation_min >= 0),
    CONSTRAINT jobs_compensation_max_nonnegative
        CHECK (compensation_max IS NULL OR compensation_max >= 0),
    CONSTRAINT jobs_compensation_range_valid
        CHECK (
            compensation_min IS NULL
            OR compensation_max IS NULL
            OR compensation_min <= compensation_max
        )
);

CREATE TABLE public.candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name text NOT NULL CHECK (length(btrim(full_name)) > 0),
    email text NOT NULL CHECK (length(btrim(email)) > 0),
    phone text,
    linkedin_url text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.applications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL
        REFERENCES public.candidates (id) ON DELETE RESTRICT,
    job_id uuid NOT NULL
        REFERENCES public.jobs (id) ON DELETE RESTRICT,
    current_stage public.application_stage NOT NULL DEFAULT 'sync_evaluation',
    agent_decision public.screening_decision,
    screening_summary text,
    hr_override_status public.screening_decision,
    examiner text NOT NULL DEFAULT 'agent'
        CHECK (length(btrim(examiner)) > 0),
    pipeline_status public.pipeline_status NOT NULL DEFAULT 'failed_at_sync',
    final_decision public.final_decision NOT NULL DEFAULT 'pending',
    remarks text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT applications_candidate_job_unique
        UNIQUE (candidate_id, job_id)
);

CREATE TABLE public.interviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL
        REFERENCES public.applications (id) ON DELETE RESTRICT,
    sequence_order integer NOT NULL CHECK (sequence_order > 0),
    scheduled_at timestamptz,
    interview_date date,
    local_audio_path text,
    feedback text,
    status public.interview_status NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT interviews_application_sequence_unique
        UNIQUE (application_id, sequence_order)
);

-- Identity lookup indexes support global matching. Email comparison is
-- case-insensitive; phone and LinkedIn are searchable but not globally unique.
CREATE UNIQUE INDEX candidates_email_lower_unique_idx
    ON public.candidates (lower(email));

CREATE INDEX candidates_phone_idx
    ON public.candidates (phone)
    WHERE phone IS NOT NULL;

CREATE INDEX candidates_linkedin_url_idx
    ON public.candidates (linkedin_url)
    WHERE linkedin_url IS NOT NULL;

CREATE INDEX jobs_status_created_at_idx
    ON public.jobs (status, created_at DESC);

-- Supports per-job passed/failed dashboards and candidate history lookups.
CREATE INDEX applications_job_pipeline_created_at_idx
    ON public.applications (job_id, pipeline_status, created_at DESC);

CREATE INDEX applications_pipeline_final_created_at_idx
    ON public.applications (pipeline_status, final_decision, created_at DESC);

CREATE INDEX applications_candidate_created_at_idx
    ON public.applications (candidate_id, created_at DESC);

-- The unique application/sequence constraint also provides the index needed
-- to list one application's interview rounds in order.

CREATE VIEW public.hr_passed_candidates_dashboard
WITH (security_invoker = true) AS
SELECT
    a.id AS application_id,
    a.candidate_id,
    a.job_id,
    c.full_name,
    c.email,
    c.phone,
    c.linkedin_url,
    j.title AS job_title,
    a.current_stage,
    a.agent_decision,
    a.screening_summary,
    a.hr_override_status,
    a.examiner,
    a.pipeline_status,
    a.final_decision,
    a.remarks,
    a.created_at AS application_created_at
FROM public.applications AS a
JOIN public.candidates AS c ON c.id = a.candidate_id
JOIN public.jobs AS j ON j.id = a.job_id
WHERE a.pipeline_status IN ('active_pipeline', 'pending_ceo_decision')
  AND a.final_decision = 'pending';

CREATE VIEW public.hr_failed_candidates_dashboard
WITH (security_invoker = true) AS
SELECT
    a.id AS application_id,
    a.candidate_id,
    a.job_id,
    c.full_name,
    c.email,
    c.phone,
    c.linkedin_url,
    j.title AS job_title,
    a.current_stage,
    a.agent_decision,
    a.screening_summary,
    a.hr_override_status,
    a.examiner,
    a.pipeline_status,
    a.final_decision,
    a.remarks,
    a.created_at AS application_created_at
FROM public.applications AS a
JOIN public.candidates AS c ON c.id = a.candidate_id
JOIN public.jobs AS j ON j.id = a.job_id
WHERE a.pipeline_status = 'failed_at_sync'
  AND a.final_decision = 'fail';

COMMENT ON VIEW public.hr_passed_candidates_dashboard IS
    'Active or pending-CEO applications that passed AI screening or were passed by HR override.';

COMMENT ON VIEW public.hr_failed_candidates_dashboard IS
    'Applications rejected at sync and not subsequently restored by HR override.';

-- These records contain candidate PII. Access is intended through the backend
-- Supabase service client; add role-specific policies with the authentication
-- implementation before granting direct end-user table access.
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interviews ENABLE ROW LEVEL SECURITY;