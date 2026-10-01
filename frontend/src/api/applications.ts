import api from './client';
import type {
  Application,
  ApplicationApplicant,
  ApplicationDossier,
  CandidateHistoryRecord,
  FinalDecision,
  PipelineStatus,
} from './types';

export async function listJobApplications(
  jobId: string,
  pipelineStatus?: PipelineStatus,
): Promise<ApplicationApplicant[]> {
  const { data } = await api.get<ApplicationApplicant[]>(
    `/api/v1/jobs/${jobId}/applications`,
    { params: pipelineStatus ? { pipeline_status: pipelineStatus } : {} },
  );
  return data;
}

export async function getCandidateHistory(candidateId: string): Promise<CandidateHistoryRecord[]> {
  const { data } = await api.get<CandidateHistoryRecord[]>(
    `/api/v1/candidates/${candidateId}/history`,
  );
  return data;
}

export async function hrOverride(applicationId: string, hrUsername: string): Promise<Application> {
  const { data } = await api.post<Application>(
    `/api/v1/applications/${applicationId}/hr-override`,
    { hr_username: hrUsername },
  );
  return data;
}

export async function moveToCeo(applicationId: string): Promise<Application> {
  const { data } = await api.post<Application>(
    `/api/v1/applications/${applicationId}/move-to-ceo`,
  );
  return data;
}

export async function getDossier(applicationId: string): Promise<ApplicationDossier> {
  const { data } = await api.get<ApplicationDossier>(
    `/api/v1/applications/${applicationId}/dossier`,
  );
  return data;
}

export async function finalDecision(
  applicationId: string,
  decision: FinalDecision,
  remarks?: string,
): Promise<Application> {
  const { data } = await api.post<Application>(
    `/api/v1/applications/${applicationId}/final-decision`,
    { final_decision: decision, remarks: remarks ?? null },
  );
  return data;
}
