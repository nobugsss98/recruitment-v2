import api from './client';
import type {
  FormSyncResult,
  GoogleFormCloneResult,
  GoogleFormQuestionSet,
  Job,
  JobCreatePayload,
  JobPatchPayload,
} from './types';

export async function listJobs(): Promise<Job[]> {
  const { data } = await api.get<Job[]>('/api/v1/jobs');
  return data;
}

export async function getJob(jobId: string): Promise<Job> {
  const { data } = await api.get<Job>(`/api/v1/jobs/${jobId}`);
  return data;
}

export async function createJob(payload: JobCreatePayload): Promise<Job> {
  const { data } = await api.post<Job>('/api/v1/jobs', payload);
  return data;
}

export async function patchJob(jobId: string, patch: JobPatchPayload): Promise<Job> {
  const { data } = await api.patch<Job>(`/api/v1/jobs/${jobId}`, patch);
  return data;
}

export async function generateJd(jobId: string): Promise<Job> {
  const { data } = await api.post<Job>(`/api/v1/jobs/${jobId}/generate-jd`);
  return data;
}

export async function generateFormQuestions(jobId: string): Promise<GoogleFormQuestionSet> {
  const { data } = await api.post<GoogleFormQuestionSet>(
    `/api/v1/jobs/${jobId}/generate-form-questions`,
  );
  return data;
}

export async function cloneForm(
  jobId: string,
  questionSet: GoogleFormQuestionSet,
): Promise<GoogleFormCloneResult> {
  const { data } = await api.post<GoogleFormCloneResult>(
    `/api/v1/jobs/${jobId}/clone-form`,
    questionSet,
  );
  return data;
}

export async function generateLinkedinBlurb(jobId: string): Promise<Job> {
  const { data } = await api.post<Job>(`/api/v1/jobs/${jobId}/linkedin-blurb`);
  return data;
}

export async function syncJob(jobId: string): Promise<FormSyncResult> {
  const { data } = await api.post<FormSyncResult>(`/api/v1/jobs/${jobId}/sync`);
  return data;
}
