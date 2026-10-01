/* Central TypeScript types mirroring the backend API contract (recruitment-v2 backend). */

export type Role = 'hr' | 'interviewer' | 'ceo';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type JobStatus = 'draft' | 'posted' | 'closed';

export interface Job {
  id: string;
  title: string;
  tech_stack: string;
  seniority: string;
  compensation_min: number | null;
  compensation_max: number | null;
  jd_markdown: string | null;
  google_form_id: string | null;
  google_form_url: string | null;
  linkedin_blurb: string | null;
  status: JobStatus;
  created_at: string;
}

export interface JobCreatePayload {
  title: string;
  tech_stack: string;
  seniority: string;
  compensation_min?: number | null;
  compensation_max?: number | null;
}

export interface JobPatchPayload {
  title?: string;
  tech_stack?: string;
  seniority?: string;
  compensation_min?: number | null;
  compensation_max?: number | null;
  jd_markdown?: string;
  google_form_id?: string;
  google_form_url?: string;
  linkedin_blurb?: string;
  status?: JobStatus;
}

export type PipelineStatus =
  | 'failed_at_sync'
  | 'active_pipeline'
  | 'pending_ceo_decision'
  | 'closed_complete';

export type ScreeningDecision = 'pass' | 'fail';
export type FinalDecision = 'pending' | 'pass' | 'fail';
export type ApplicationStage =
  | 'sync_evaluation'
  | 'technical_interview'
  | 'ceo_review'
  | 'closed';

export interface Application {
  id: string;
  candidate_id: string;
  job_id: string;
  current_stage: ApplicationStage;
  agent_decision: ScreeningDecision | null;
  screening_summary: string | null;
  hr_override_status: ScreeningDecision | null;
  examiner: string;
  pipeline_status: PipelineStatus;
  final_decision: FinalDecision;
  remarks: string | null;
  created_at: string;
  google_form_response_id: string | null;
  form_responses: Record<string, string>;
}

export interface ApplicationApplicant extends Application {
  candidate_name: string;
  email: string;
  phone: string | null;
}

export interface InterviewRound {
  id: string;
  application_id: string;
  sequence_order: number;
  scheduled_at: string | null;
  interview_date: string | null;
  local_audio_path: string | null;
  feedback: string | null;
  status: 'pending' | 'complete';
  created_at: string;
}

export interface FormSyncItem {
  response_id: string;
  candidate_name: string | null;
  email: string | null;
  application_id: string | null;
  agent_decision: ScreeningDecision | null;
  pipeline_status: PipelineStatus | null;
  screening_summary: string | null;
  status: 'synced' | 'duplicate' | 'error';
  detail: string | null;
}

export interface FormSyncResult {
  total_responses: number;
  synced: number;
  skipped_duplicates: number;
  errors: number;
  items: FormSyncItem[];
}

export interface CandidateHistoryRecord {
  application_id: string;
  job_id: string;
  job_title: string;
  current_stage: ApplicationStage;
  pipeline_status: PipelineStatus;
  final_decision: FinalDecision;
  remarks: string | null;
  screening_summary: string | null;
  created_at: string;
}

export interface ApplicationDossier {
  application: Application;
  interviews: InterviewRound[];
}

export type GoogleFormQuestionType =
  | 'short_text'
  | 'paragraph'
  | 'multiple_choice'
  | 'checkbox';

export interface GoogleFormQuestion {
  title: string;
  question_type: GoogleFormQuestionType;
  options: string[];
  required: boolean;
}

export interface GoogleFormQuestionSet {
  questions: GoogleFormQuestion[];
}

export interface GoogleFormCloneResult {
  form_id: string;
  responder_url: string;
  editor_url: string;
  questions_added: number;
}

export interface ApiErrorBody {
  detail?: string | { msg?: string }[];
}

export function apiErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: ApiErrorBody; status?: number } }).response;
    const detail = resp?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (typeof first === 'string') return first;
      if (typeof first?.msg === 'string') return first.msg;
    }
    if (resp?.status) return `Request failed (${resp.status})`;
  }
  if (err instanceof Error) return err.message;
  return 'Something went wrong';
}
