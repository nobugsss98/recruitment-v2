import api from './client';
import type { InterviewRound } from './types';

export async function listInterviews(applicationId: string): Promise<InterviewRound[]> {
  const { data } = await api.get<InterviewRound[]>(
    `/api/v1/applications/${applicationId}/interviews`,
  );
  return data;
}

export async function scheduleInterview(
  applicationId: string,
  scheduledAtIso: string,
): Promise<InterviewRound> {
  const { data } = await api.post<InterviewRound>(
    `/api/v1/applications/${applicationId}/interviews`,
    { scheduled_at: scheduledAtIso },
  );
  return data;
}

export interface InterviewUpdate {
  interview_date?: string;
  feedback?: string;
  status?: 'pending' | 'complete';
}

export async function updateInterview(
  interviewId: string,
  update: InterviewUpdate,
): Promise<InterviewRound> {
  const { data } = await api.patch<InterviewRound>(`/api/v1/interviews/${interviewId}`, update);
  return data;
}

export async function deleteInterview(interviewId: string): Promise<void> {
  await api.delete(`/api/v1/interviews/${interviewId}`);
}

/**
 * Upload a recording for an interview round. The backend requires a
 * multipart body with both `recording` (the file) and `interview_date`.
 */
export async function uploadRecording(
  interviewId: string,
  interviewDate: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<InterviewRound> {
  const form = new FormData();
  form.append('recording', file, file.name);
  form.append('interview_date', interviewDate);
  const { data } = await api.post<InterviewRound>(
    `/api/v1/interviews/${interviewId}/recording`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (evt.total && onProgress) {
          onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      },
    },
  );
  return data;
}
