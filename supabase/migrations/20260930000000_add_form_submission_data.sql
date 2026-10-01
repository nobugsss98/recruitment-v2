ALTER TABLE public.applications
    ADD COLUMN google_form_response_id text,
    ADD COLUMN form_responses jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX applications_job_form_response_unique_idx
    ON public.applications (job_id, google_form_response_id)
    WHERE google_form_response_id IS NOT NULL;