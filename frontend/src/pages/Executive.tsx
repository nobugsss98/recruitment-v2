import { useMemo, useState } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { toast } from 'sonner';
import * as jobsApi from '../api/jobs';
import * as appsApi from '../api/applications';
import {
  apiErrorMessage,
  type Application,
  type ApplicationDossier,
  type FinalDecision,
} from '../api/types';
import { useAuth } from '../context/AuthContext';
import { Button, Drawer, Modal, inputClass, labelClass } from '../components/primitives';
import { PageShell, PageHeader, Card, Skeleton, EmptyState, Stagger, StaggerItem } from '../components/ui';
import { StatusBadge } from '../components/StatusBadge';

function DecisionModal({
  open,
  onClose,
  decision,
  applicationId,
}: {
  open: boolean;
  onClose: () => void;
  decision: FinalDecision;
  applicationId: string | null;
}) {
  const queryClient = useQueryClient();
  const [remarks, setRemarks] = useState('');

  const mutation = useMutation({
    mutationFn: () => appsApi.finalDecision(applicationId!, decision, remarks || undefined),
    onSuccess: () => {
      toast.success(decision === 'pass' ? 'Candidate approved 🎉' : 'Candidate rejected');
      queryClient.invalidateQueries({ queryKey: ['ceo-queue'] });
      queryClient.invalidateQueries({ queryKey: ['dossier', applicationId] });
      onClose();
      setRemarks('');
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const isPass = decision === 'pass';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isPass ? '✅ Approve candidate' : '❌ Reject candidate'}
      subtitle="Your decision and remarks are recorded permanently."
    >
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Remarks</label>
          <textarea
            rows={4}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder={isPass ? 'Why are they a great hire?' : 'What was the deciding factor?'}
            className={inputClass}
          />
        </div>
        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={isPass ? 'success' : 'danger'}
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
          >
            Confirm {isPass ? 'approval' : 'rejection'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function DossierDrawer({
  applicationId,
  jobTitle,
  candidateName,
  onClose,
}: {
  applicationId: string | null;
  jobTitle: string;
  candidateName: string;
  onClose: () => void;
}) {
  const { hasRole } = useAuth();
  const [decision, setDecision] = useState<FinalDecision | null>(null);

  const { data: dossier, isLoading } = useQuery({
    queryKey: ['dossier', applicationId],
    queryFn: () => appsApi.getDossier(applicationId!),
    enabled: Boolean(applicationId),
  });

  return (
    <>
      <Drawer
        open={Boolean(applicationId)}
        onClose={onClose}
        title={candidateName}
        subtitle={`${jobTitle} · executive dossier`}
      >
        {isLoading || !dossier ? (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : (
          <DossierBody dossier={dossier} />
        )}
        {dossier && hasRole('ceo') && dossier.application.pipeline_status === 'pending_ceo_decision' && (
          <div className="sticky bottom-0 -mx-6 mt-6 border-t border-white/10 bg-surface-900/95 px-6 py-4 backdrop-blur">
            <div className="flex gap-3">
              <Button variant="success" className="flex-1" onClick={() => setDecision('pass')}>
                ✅ Approve
              </Button>
              <Button variant="danger" className="flex-1" onClick={() => setDecision('fail')}>
                ❌ Reject
              </Button>
            </div>
          </div>
        )}
      </Drawer>
      <DecisionModal
        open={decision !== null}
        onClose={() => setDecision(null)}
        decision={decision ?? 'pass'}
        applicationId={applicationId}
      />
    </>
  );
}

function DossierBody({ dossier }: { dossier: ApplicationDossier }) {
  const app = dossier.application;
  const formEntries = Object.entries(app.form_responses ?? {});
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={app.pipeline_status} />
        {app.agent_decision && <StatusBadge value={app.agent_decision} />}
        {app.hr_override_status && <StatusBadge value={app.hr_override_status} />}
        <StatusBadge value={app.final_decision} />
      </div>

      <section>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
          AI screening summary
        </h3>
        <p className="rounded-xl bg-white/[0.03] p-4 text-sm leading-relaxed text-slate-200">
          {app.screening_summary ?? '—'}
        </p>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
          Interview rounds ({dossier.interviews.length})
        </h3>
        <div className="space-y-3">
          {dossier.interviews.length === 0 && (
            <p className="text-sm text-slate-500">No rounds recorded.</p>
          )}
          {dossier.interviews.map((r) => (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-bold text-white">Round {r.sequence_order}</span>
                <StatusBadge value={r.status} />
              </div>
              <div className="mb-2 text-xs text-slate-400">
                {r.scheduled_at ? new Date(r.scheduled_at).toLocaleString() : 'Unscheduled'}
              </div>
              {r.feedback ? (
                <p className="text-sm text-slate-200">{r.feedback}</p>
              ) : (
                <p className="text-sm italic text-slate-500">No feedback yet.</p>
              )}
              {r.local_audio_path && (
                <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                  🎙️ <span className="truncate font-mono">{r.local_audio_path}</span>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </section>

      {formEntries.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
            Form answers
          </h3>
          <div className="space-y-2">
            {formEntries.map(([q, a]) => (
              <div key={q} className="rounded-xl bg-white/[0.03] p-3.5">
                <div className="mb-1 text-xs font-semibold text-indigo-300">{q}</div>
                <div className="text-sm text-slate-200">{a}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {app.remarks && (
        <section>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
            Decision remarks
          </h3>
          <p className="rounded-xl bg-white/[0.03] p-4 text-sm text-slate-200">{app.remarks}</p>
        </section>
      )}
    </div>
  );
}

export function ExecutivePage() {
  const { hasRole } = useAuth();
  const [selected, setSelected] = useState<{
    id: string;
    jobTitle: string;
    candidateName: string;
  } | null>(null);

  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: jobsApi.listJobs });

  const queueQueries = useQueries({
    queries: (jobs ?? []).map((job) => ({
      queryKey: ['ceo-queue', job.id],
      queryFn: () => appsApi.listJobApplications(job.id, 'pending_ceo_decision'),
      staleTime: 30_000,
    })),
  });

  const queue = useMemo(() => {
    const items: { app: Application; jobTitle: string }[] = [];
    queueQueries.forEach((q, i) => {
      const job = jobs?.[i];
      (q.data ?? []).forEach((app) => {
        items.push({ app, jobTitle: job?.title ?? 'Unknown job' });
      });
    });
    return items.sort(
      (a, b) => new Date(b.app.created_at).getTime() - new Date(a.app.created_at).getTime(),
    );
  }, [queueQueries, jobs]);

  const loading = queueQueries.some((q) => q.isLoading);

  return (
    <PageShell wide>
      <PageHeader
        title="Executive review 👑"
        subtitle="Final sign-off on candidates who cleared every interview round."
      />

      {loading ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="p-6">
              <Skeleton className="mb-3 h-6 w-3/4" />
              <Skeleton className="mb-4 h-4 w-1/2" />
              <Skeleton className="h-20 w-full" />
            </Card>
          ))}
        </div>
      ) : queue.length > 0 ? (
        <Stagger>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {queue.map(({ app, jobTitle }, i) => (
              <StaggerItem key={app.id}>
                <motion.div
                  whileHover={{ y: -5, transition: { duration: 0.2 } }}
                  onClick={() =>
                    setSelected({
                      id: app.id,
                      jobTitle,
                      candidateName: (app as { candidate_name?: string }).candidate_name ?? 'Candidate',
                    })
                  }
                  className="h-full cursor-pointer overflow-hidden rounded-2xl border border-amber-500/20 bg-gradient-to-br from-surface-850 to-surface-900 p-6 transition hover:border-amber-400/50 hover:shadow-glow"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-widest text-amber-300/80">
                      Awaiting decision
                    </span>
                    <span className="text-xs text-slate-500">#{i + 1}</span>
                  </div>
                  <h3 className="mb-1 text-xl font-bold text-white">
                    {(app as { candidate_name?: string }).candidate_name ?? 'Candidate'}
                  </h3>
                  <p className="mb-4 text-sm text-slate-400">{jobTitle}</p>
                  {app.screening_summary && (
                    <p className="mb-4 line-clamp-3 text-sm text-slate-300">{app.screening_summary}</p>
                  )}
                  <div className="flex items-center justify-between">
                    <StatusBadge value={app.pipeline_status} />
                    <span className="text-sm font-semibold text-amber-300">Review dossier →</span>
                  </div>
                </motion.div>
              </StaggerItem>
            ))}
          </div>
        </Stagger>
      ) : (
        <EmptyState
          icon="👑"
          title="Queue is clear"
          hint="No candidates are waiting for executive review right now."
        />
      )}

      <AnimatePresence>
        {selected && (
          <DossierDrawer
            applicationId={selected.id}
            jobTitle={selected.jobTitle}
            candidateName={selected.candidateName}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>

      {!hasRole('ceo') && queue.length > 0 && (
        <p className="mt-6 text-center text-xs text-slate-500">
          You are viewing in read-only mode — only the CEO can approve or reject.
        </p>
      )}
    </PageShell>
  );
}
