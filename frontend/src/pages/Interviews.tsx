import { useMemo, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { toast } from 'sonner';
import * as jobsApi from '../api/jobs';
import * as appsApi from '../api/applications';
import * as interviewsApi from '../api/interviews';
import { apiErrorMessage, type InterviewRound } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { Button, Modal, inputClass, labelClass } from '../components/primitives';
import { PageShell, PageHeader, Card, Skeleton, EmptyState } from '../components/ui';
import { StatusBadge } from '../components/StatusBadge';

function ScheduleModal({
  open,
  onClose,
  applicationId,
  nextOrder,
}: {
  open: boolean;
  onClose: () => void;
  applicationId: string;
  nextOrder: number;
}) {
  const queryClient = useQueryClient();
  const [dt, setDt] = useState('');

  const mutation = useMutation({
    mutationFn: () => interviewsApi.scheduleInterview(applicationId, new Date(dt).toISOString()),
    onSuccess: (round) => {
      toast.success(`Round ${round.sequence_order} scheduled`);
      queryClient.invalidateQueries({ queryKey: ['interviews', applicationId] });
      onClose();
      setDt('');
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!dt) {
      toast.error('Pick a date and time first');
      return;
    }
    mutation.mutate();
  };

  return (
    <Modal open={open} onClose={onClose} title={`Schedule round ${nextOrder}`} subtitle="Pick a date and time — times are stored timezone-aware.">
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className={labelClass}>Scheduled at</label>
          <input
            type="datetime-local"
            value={dt}
            onChange={(e) => setDt(e.target.value)}
            className={inputClass}
          />
        </div>
        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Schedule round
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function RoundCard({
  round,
  applicationId,
}: {
  round: InterviewRound;
  applicationId: string;
}) {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [feedback, setFeedback] = useState(round.feedback ?? '');
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['interviews', applicationId] });
  };

  const saveFeedback = useMutation({
    mutationFn: (markComplete: boolean) =>
      interviewsApi.updateInterview(round.id, {
        feedback: feedback || undefined,
        ...(markComplete ? { status: 'complete' as const } : {}),
      }),
    onSuccess: (_, markComplete) => {
      toast.success(markComplete ? 'Round marked complete' : 'Feedback saved');
      invalidate();
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const remove = useMutation({
    mutationFn: () => interviewsApi.deleteInterview(round.id),
    onSuccess: () => {
      toast.success('Round deleted');
      invalidate();
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const upload = useMutation({
    mutationFn: (file: File) =>
      interviewsApi.uploadRecording(
        round.id,
        new Date().toISOString().slice(0, 10),
        file,
        setUploadPct,
      ),
    onSuccess: () => {
      toast.success('Recording uploaded & verified');
      setUploadPct(null);
      invalidate();
    },
    onError: (err) => {
      setUploadPct(null);
      toast.error(apiErrorMessage(err));
    },
  });

  const feedbackDirty = feedback !== (round.feedback ?? '');
  const complete = round.status === 'complete';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      className={`relative overflow-hidden rounded-2xl border p-6 ${
        complete
          ? 'border-emerald-500/25 bg-emerald-500/[0.04]'
          : 'border-white/10 bg-surface-850/80'
      }`}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-4">
          <div
            className={`flex h-12 w-12 items-center justify-center rounded-2xl text-lg font-extrabold text-white ${
              complete
                ? 'bg-gradient-to-br from-emerald-500 to-teal-600'
                : 'bg-gradient-to-br from-indigo-500 to-violet-600 shadow-glow'
            }`}
          >
            {round.sequence_order}
          </div>
          <div>
            <div className="font-bold text-white">Round {round.sequence_order}</div>
            <div className="text-xs text-slate-400">
              {round.scheduled_at
                ? new Date(round.scheduled_at).toLocaleString()
                : 'Not scheduled'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge value={round.status} />
          {hasRole('hr') && (
            <button
              onClick={() => {
                if (confirm(`Delete round ${round.sequence_order}?`)) remove.mutate();
              }}
              disabled={remove.isPending}
              className="rounded-lg p-1.5 text-slate-500 transition hover:bg-rose-500/15 hover:text-rose-300"
              title="Delete round"
            >
              🗑️
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <label className={labelClass}>Interviewer feedback</label>
          <textarea
            rows={4}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="How did the candidate do? Strengths, concerns, verdict…"
            className={inputClass}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={!feedbackDirty || saveFeedback.isPending}
            onClick={() => saveFeedback.mutate(false)}
            loading={saveFeedback.isPending && !complete}
          >
            💾 Save feedback
          </Button>
          {!complete && (
            <Button
              variant="success"
              size="sm"
              onClick={() => saveFeedback.mutate(true)}
              loading={saveFeedback.isPending}
            >
              ✅ Mark complete
            </Button>
          )}
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-500">
              Audio recording
            </span>
            {round.local_audio_path && (
              <span className="text-xs text-emerald-300">✓ saved</span>
            )}
          </div>
          {round.local_audio_path && (
            <div className="mb-2 truncate font-mono text-xs text-slate-400">
              {round.local_audio_path}
            </div>
          )}
          {hasRole('hr') && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="audio/mpeg,audio/mp3,.mp3"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload.mutate(f);
                  e.target.value = '';
                }}
              />
              {uploadPct === null ? (
                <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()} loading={upload.isPending}>
                  🎙️ Upload MP3
                </Button>
              ) : (
                <div className="space-y-1.5">
                  <div className="h-2 overflow-hidden rounded-full bg-white/10">
                    <motion.div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-violet-500"
                      animate={{ width: `${uploadPct}%` }}
                      transition={{ ease: 'easeOut' }}
                    />
                  </div>
                  <div className="text-xs text-slate-400">Uploading… {uploadPct}%</div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export function InterviewsPage() {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState('');
  const [applicationId, setApplicationId] = useState('');
  const [scheduleOpen, setScheduleOpen] = useState(false);

  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: jobsApi.listJobs });

  const { data: applications, isLoading: appsLoading } = useQuery({
    queryKey: ['job-applications', jobId],
    queryFn: () => appsApi.listJobApplications(jobId, 'active_pipeline'),
    enabled: Boolean(jobId),
  });

  const selectedApp = useMemo(
    () => (applications ?? []).find((a) => a.id === applicationId) ?? null,
    [applications, applicationId],
  );

  const { data: rounds, isLoading: roundsLoading } = useQuery({
    queryKey: ['interviews', applicationId],
    queryFn: () => interviewsApi.listInterviews(applicationId),
    enabled: Boolean(applicationId),
  });

  const nextOrder = (rounds?.length ?? 0) + 1;
  const allComplete = rounds && rounds.length > 0 && rounds.every((r) => r.status === 'complete');

  const moveToCeo = useMutation({
    mutationFn: () => appsApi.moveToCeo(applicationId),
    onSuccess: () => {
      toast.success('Moved to CEO review');
      queryClient.invalidateQueries({ queryKey: ['job-applications', jobId] });
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  return (
    <PageShell wide>
      <PageHeader
        title="Interviews"
        subtitle="Schedule rounds, capture feedback, and upload recordings."
        actions={
          selectedApp && hasRole('hr') ? (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setScheduleOpen(true)}>
                ＋ Schedule round
              </Button>
              <Button
                variant="success"
                disabled={!allComplete || moveToCeo.isPending}
                onClick={() => moveToCeo.mutate()}
                loading={moveToCeo.isPending}
                title={allComplete ? 'Send to CEO review' : 'All rounds must be complete first'}
              >
                👑 Move to CEO review
              </Button>
            </div>
          ) : undefined
        }
      />

      <Card className="mb-6 p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className={labelClass}>Job</label>
            <select
              value={jobId}
              onChange={(e) => {
                setJobId(e.target.value);
                setApplicationId('');
              }}
              className={inputClass}
            >
              <option value="">Select a job…</option>
              {(jobs ?? []).map((j) => (
                <option key={j.id} value={j.id}>
                  {j.title} ({j.status})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>Application</label>
            <select
              value={applicationId}
              onChange={(e) => setApplicationId(e.target.value)}
              disabled={!jobId || appsLoading}
              className={inputClass}
            >
              <option value="">
                {appsLoading ? 'Loading…' : 'Select an applicant…'}
              </option>
              {(applications ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.candidate_name} — {a.email}
                </option>
              ))}
            </select>
          </div>
        </div>
        {jobId && !appsLoading && (applications?.length ?? 0) === 0 && (
          <p className="mt-3 text-sm text-slate-500">
            No active-pipeline applications for this job.
          </p>
        )}
      </Card>

      {selectedApp && (
        <div className="mb-6 flex items-center gap-3 rounded-2xl border border-indigo-500/25 bg-indigo-500/[0.06] px-5 py-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white">
            {selectedApp.candidate_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="font-bold text-white">{selectedApp.candidate_name}</div>
            <div className="text-xs text-slate-400">
              {selectedApp.email} · {rounds?.length ?? 0} round{(rounds?.length ?? 0) === 1 ? '' : 's'}
            </div>
          </div>
          <div className="ml-auto">
            <StatusBadge value={selectedApp.pipeline_status} />
          </div>
        </div>
      )}

      {!selectedApp ? (
        <EmptyState
          icon="🎙️"
          title="Pick an application"
          hint="Choose a job, then an applicant, to manage their interview rounds."
        />
      ) : roundsLoading ? (
        <div className="space-y-4">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-56 w-full" />
          ))}
        </div>
      ) : rounds && rounds.length > 0 ? (
        <div className="relative">
          {/* Timeline spine */}
          <div className="absolute bottom-8 left-[49px] top-8 w-px bg-gradient-to-b from-indigo-500/50 via-violet-500/30 to-transparent" />
          <div className="space-y-5">
            <AnimatePresence initial={false}>
              {rounds.map((r) => (
                <div key={r.id} className="relative pl-2">
                  <RoundCard round={r} applicationId={applicationId} />
                </div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      ) : (
        <EmptyState
          icon="📅"
          title="No rounds yet"
          hint="Schedule the first interview round for this candidate."
          action={
            hasRole('hr') ? (
              <Button onClick={() => setScheduleOpen(true)}>＋ Schedule round 1</Button>
            ) : undefined
          }
        />
      )}

      {selectedApp && (
        <ScheduleModal
          open={scheduleOpen}
          onClose={() => setScheduleOpen(false)}
          applicationId={applicationId}
          nextOrder={nextOrder}
        />
      )}
    </PageShell>
  );
}
