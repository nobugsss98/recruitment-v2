import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { toast } from 'sonner';
import * as jobsApi from '../api/jobs';
import * as appsApi from '../api/applications';
import {
  apiErrorMessage,
  type ApplicationApplicant,
  type CandidateHistoryRecord,
  type FormSyncResult,
  type PipelineStatus,
} from '../api/types';
import { useAuth } from '../context/AuthContext';
import { Button, Drawer, inputClass, Modal } from '../components/primitives';
import { PageShell, PageHeader, Card, Skeleton, EmptyState } from '../components/ui';
import { StatusBadge, pipelineViewOptions, type PipelineView } from '../components/StatusBadge';

function SyncProgressModal({
  open,
  onClose,
  result,
  syncing,
}: {
  open: boolean;
  onClose: () => void;
  result: FormSyncResult | null;
  syncing: boolean;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Syncing responses" subtitle="Pulling Google Form answers and screening with AI" maxWidth="max-w-2xl">
      {syncing && !result && (
        <div className="space-y-6 py-4">
          <div className="flex items-center gap-4">
            <span className="h-8 w-8 animate-spin rounded-full border-[3px] border-indigo-400/30 border-t-indigo-300" />
            <div>
              <div className="font-semibold text-white">Reading form responses…</div>
              <div className="text-sm text-slate-400">AI is scoring each applicant against the JD.</div>
            </div>
          </div>
          {/* Animated indeterminate progress */}
          <div className="h-2.5 overflow-hidden rounded-full bg-white/10">
            <motion.div
              className="h-full w-1/3 rounded-full bg-gradient-to-r from-indigo-400 to-violet-500"
              animate={{ x: ['-100%', '300%'] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
            />
          </div>
          <div className="space-y-2">
            {['Fetching new responses', 'Deduplicating candidates', 'AI screening pass/fail', 'Writing results'].map(
              (step, i) => (
                <motion.div
                  key={step}
                  initial={{ opacity: 0.3 }}
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 2, repeat: Infinity, delay: i * 0.5 }}
                  className="flex items-center gap-2 text-sm text-slate-300"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
                  {step}
                </motion.div>
              ),
            )}
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-5">
          <div className="grid grid-cols-4 gap-3 text-center">
            {[
              { label: 'Total', value: result.total_responses, color: 'text-white' },
              { label: 'Synced', value: result.synced, color: 'text-emerald-300' },
              { label: 'Duplicates', value: result.skipped_duplicates, color: 'text-slate-300' },
              { label: 'Errors', value: result.errors, color: 'text-rose-300' },
            ].map((s) => (
              <div key={s.label} className="rounded-xl bg-white/5 p-4">
                <div className={`text-3xl font-extrabold ${s.color}`}>{s.value}</div>
                <div className="mt-1 text-xs text-slate-400">{s.label}</div>
              </div>
            ))}
          </div>
          {result.items.length > 0 && (
            <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {result.items.map((item) => (
                <div
                  key={item.response_id}
                  className="flex items-center justify-between gap-3 rounded-xl bg-white/[0.03] px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">
                      {item.candidate_name ?? item.email ?? item.response_id}
                    </div>
                    {item.detail && <div className="truncate text-xs text-slate-400">{item.detail}</div>}
                  </div>
                  <StatusBadge value={item.status} dot={false} />
                </div>
              ))}
            </div>
          )}
          <div className="flex justify-end">
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function CandidateDrawer({
  application,
  onClose,
  onUpdated,
}: {
  application: ApplicationApplicant | null;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const { user, hasRole } = useAuth();
  const [history, setHistory] = useState<CandidateHistoryRecord[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [overrideBusy, setOverrideBusy] = useState(false);

  const loadHistory = async () => {
    if (!application || history) return;
    setHistoryLoading(true);
    try {
      setHistory(await appsApi.getCandidateHistory(application.candidate_id));
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleOverride = async () => {
    if (!application || !user) return;
    setOverrideBusy(true);
    try {
      await appsApi.hrOverride(application.id, user.full_name);
      toast.success('HR override applied — candidate moved to pipeline');
      onUpdated();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setOverrideBusy(false);
    }
  };

  const formEntries = application ? Object.entries(application.form_responses ?? {}) : [];
  const canOverride =
    hasRole('hr') && application?.pipeline_status === 'failed_at_sync';

  return (
    <Drawer
      open={Boolean(application)}
      onClose={onClose}
      title={application?.candidate_name ?? ''}
      subtitle={application?.email}
    >
      {application && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge value={application.pipeline_status} />
            {application.agent_decision && <StatusBadge value={application.agent_decision} />}
            {application.hr_override_status && (
              <span className="rounded-full border border-amber-400/30 bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-300">
                HR override: {application.hr_override_status}
              </span>
            )}
          </div>

          <section>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
              Screening summary
            </h3>
            <p className="rounded-xl bg-white/[0.03] p-4 text-sm leading-relaxed text-slate-200">
              {application.screening_summary ?? 'No summary available.'}
            </p>
          </section>

          <section>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
              Candidate
            </h3>
            <div className="space-y-1.5 rounded-xl bg-white/[0.03] p-4 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Phone</span><span className="text-white">{application.phone ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Stage</span><span className="text-white capitalize">{application.current_stage.replace(/_/g, ' ')}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Examiner</span><span className="text-white">{application.examiner}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Applied</span><span className="text-white">{new Date(application.created_at).toLocaleDateString()}</span></div>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">
              Form answers ({formEntries.length})
            </h3>
            {formEntries.length > 0 ? (
              <div className="space-y-2">
                {formEntries.map(([q, a]) => (
                  <div key={q} className="rounded-xl bg-white/[0.03] p-3.5">
                    <div className="mb-1 text-xs font-semibold text-indigo-300">{q}</div>
                    <div className="text-sm text-slate-200">{a}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No form answers recorded.</p>
            )}
          </section>

          <section>
            <button
              onClick={() => {
                void loadHistory();
              }}
              className="mb-2 flex w-full items-center justify-between text-xs font-bold uppercase tracking-widest text-slate-500 transition hover:text-white"
            >
              Sibling applications {historyLoading ? '(loading…)' : history ? `(${history.length})` : '(tap to load)'}
              <span>▾</span>
            </button>
            {history && (
              <div className="space-y-2">
                {history.length === 0 && <p className="text-sm text-slate-500">No other applications.</p>}
                {history.map((h) => (
                  <div key={h.application_id} className="rounded-xl bg-white/[0.03] p-3.5">
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-white">{h.job_title}</span>
                      <StatusBadge value={h.pipeline_status} />
                    </div>
                    {h.screening_summary && (
                      <p className="line-clamp-2 text-xs text-slate-400">{h.screening_summary}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {canOverride && (
            <div className="rounded-2xl border border-amber-500/25 bg-amber-500/5 p-4">
              <div className="mb-1 text-sm font-semibold text-amber-200">HR override</div>
              <p className="mb-3 text-xs text-slate-400">
                This candidate failed AI screening. Override to move them into the interview pipeline anyway.
              </p>
              <Button variant="secondary" loading={overrideBusy} onClick={() => void handleOverride()}>
                ⚡ Override & move to pipeline
              </Button>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}

export function ScreeningPage() {
  const { id } = useParams<{ id: string }>();
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [view, setView] = useState<PipelineView>('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<ApplicationApplicant | null>(null);
  const [syncOpen, setSyncOpen] = useState(false);
  const [syncResult, setSyncResult] = useState<FormSyncResult | null>(null);

  const { data: job } = useQuery({
    queryKey: ['job', id],
    queryFn: () => jobsApi.getJob(id!),
    enabled: Boolean(id),
  });

  const pipelineParam: PipelineStatus | undefined =
    view === 'all' ? undefined : (view as PipelineStatus);

  const { data: applications, isLoading } = useQuery({
    queryKey: ['job-applications', id, pipelineParam],
    queryFn: () => appsApi.listJobApplications(id!, pipelineParam),
    enabled: Boolean(id),
  });

  const sync = useMutation({
    mutationFn: () => jobsApi.syncJob(id!),
    onMutate: () => {
      setSyncResult(null);
      setSyncOpen(true);
    },
    onSuccess: (result) => {
      setSyncResult(result);
      queryClient.invalidateQueries({ queryKey: ['job-applications', id] });
      toast.success(`Synced ${result.synced} new applicant${result.synced === 1 ? '' : 's'}`);
    },
    onError: (err) => {
      setSyncOpen(false);
      toast.error(apiErrorMessage(err));
    },
  });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return applications ?? [];
    return (applications ?? []).filter(
      (a) =>
        a.candidate_name.toLowerCase().includes(q) || a.email.toLowerCase().includes(q),
    );
  }, [applications, search]);

  const counts = useMemo(() => {
    // Counts come from the unfiltered list — refetch per chip is wasteful,
    // so derive "all" only and show it; chips drive the server filter.
    return { total: applications?.length ?? 0 };
  }, [applications]);

  return (
    <PageShell wide>
      <div className="mb-6">
        <Link to={`/jobs/${id}`} className="text-sm text-slate-400 transition hover:text-white">
          ← {job?.title ?? 'Job'}
        </Link>
      </div>
      <PageHeader
        title="Screening"
        subtitle={job ? `AI-screened applicants for “${job.title}”` : 'Loading job…'}
        actions={
          hasRole('hr') && (
            <Button onClick={() => sync.mutate()} loading={sync.isPending && !syncOpen}>
              🔄 Sync responses
            </Button>
          )
        }
      />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-4">
          <div className="flex flex-wrap gap-1 rounded-xl bg-white/5 p-1">
            {pipelineViewOptions.map((opt) => (
              <button
                key={opt.id}
                onClick={() => setView(opt.id)}
                className={`relative rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  view === opt.id ? 'text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {view === opt.id && (
                  <motion.span
                    layoutId="filter-chip"
                    className="absolute inset-0 rounded-lg bg-gradient-to-r from-indigo-500/50 to-violet-500/40"
                    transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                  />
                )}
                <span className="relative">{opt.label}</span>
              </button>
            ))}
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="🔍 Search name or email…"
            className={`${inputClass} max-w-xs`}
          />
        </div>

        {isLoading ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : filtered.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-3 font-semibold">Candidate</th>
                  <th className="px-5 py-3 font-semibold">AI decision</th>
                  <th className="px-5 py-3 font-semibold">Pipeline</th>
                  <th className="px-5 py-3 font-semibold">Summary</th>
                  <th className="px-5 py-3 font-semibold">Applied</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {filtered.map((a, i) => (
                    <motion.tr
                      key={a.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.25 }}
                      onClick={() => setSelected(a)}
                      className="cursor-pointer border-b border-white/5 transition hover:bg-indigo-500/[0.06]"
                    >
                      <td className="px-5 py-3.5">
                        <div className="font-semibold text-white">{a.candidate_name}</div>
                        <div className="text-xs text-slate-400">{a.email}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusBadge value={a.hr_override_status ?? a.agent_decision} />
                        {a.hr_override_status && (
                          <div className="mt-1 text-[11px] text-amber-300">HR override</div>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusBadge value={a.pipeline_status} />
                      </td>
                      <td className="max-w-xs px-5 py-3.5">
                        <div className="line-clamp-2 text-xs text-slate-400">
                          {a.screening_summary ?? '—'}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-xs text-slate-400">
                        {new Date(a.created_at).toLocaleDateString()}
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6">
            <EmptyState
              icon="👥"
              title="No applicants here"
              hint={
                hasRole('hr')
                  ? 'Hit “Sync responses” to pull the latest Google Form answers and run AI screening.'
                  : 'No applicants match this view yet.'
              }
            />
          </div>
        )}

        {!isLoading && filtered.length > 0 && (
          <div className="border-t border-white/10 px-5 py-3 text-xs text-slate-500">
            Showing {filtered.length} of {counts.total} applicant{counts.total === 1 ? '' : 's'}
          </div>
        )}
      </Card>

      <CandidateDrawer
        application={selected}
        onClose={() => setSelected(null)}
        onUpdated={() => {
          queryClient.invalidateQueries({ queryKey: ['job-applications', id] });
          setSelected(null);
        }}
      />

      <SyncProgressModal
        open={syncOpen}
        onClose={() => setSyncOpen(false)}
        result={syncResult}
        syncing={sync.isPending}
      />
    </PageShell>
  );
}
