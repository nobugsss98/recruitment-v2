import { useMemo } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Bar, BarChart, Cell, ResponsiveContainer } from 'recharts';
import { toast } from 'sonner';
import * as jobsApi from '../api/jobs';
import * as appsApi from '../api/applications';
import { apiErrorMessage, type Job, type PipelineStatus } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { useCountUp } from '../hooks/useCountUp';
import { Button, Modal, inputClass, labelClass } from '../components/primitives';
import { PageShell, PageHeader, Card, Skeleton, EmptyState, Stagger, StaggerItem } from '../components/ui';
import { StatusBadge } from '../components/StatusBadge';
import { useState, type FormEvent } from 'react';

function usePipelineCounts(jobId: string) {
  return useQuery({
    queryKey: ['job-applications', jobId],
    queryFn: () => appsApi.listJobApplications(jobId),
    staleTime: 30_000,
  });
}

const chartColors: Record<PipelineStatus, string> = {
  active_pipeline: '#38bdf8',
  failed_at_sync: '#fb7185',
  pending_ceo_decision: '#fbbf24',
  closed_complete: '#34d399',
};

function JobCard({ job }: { job: Job }) {
  const { data: applications, isLoading } = usePipelineCounts(job.id);

  const counts = useMemo(() => {
    const c: Record<PipelineStatus, number> = {
      active_pipeline: 0,
      failed_at_sync: 0,
      pending_ceo_decision: 0,
      closed_complete: 0,
    };
    (applications ?? []).forEach((a) => {
      c[a.pipeline_status] += 1;
    });
    return c;
  }, [applications]);

  const chartData = useMemo(
    () =>
      (Object.keys(counts) as PipelineStatus[]).map((k) => ({
        name: k,
        value: counts[k],
      })),
    [counts],
  );

  const total = chartData.reduce((s, d) => s + d.value, 0);
  const comp =
    job.compensation_min != null || job.compensation_max != null
      ? `$${job.compensation_min?.toLocaleString() ?? '—'} – $${job.compensation_max?.toLocaleString() ?? '—'}`
      : null;

  return (
    <Link to={`/jobs/${job.id}`}>
      <motion.div
        whileHover={{ y: -5, transition: { duration: 0.2 } }}
        className="group h-full overflow-hidden rounded-2xl border border-white/10 bg-surface-850/80 backdrop-blur-sm transition-colors hover:border-indigo-400/40 hover:shadow-glow"
      >
        <div className="p-6">
          <div className="mb-3 flex items-start justify-between gap-3">
            <h3 className="text-lg font-bold leading-snug text-white transition group-hover:text-indigo-200">
              {job.title}
            </h3>
            <StatusBadge value={job.status} />
          </div>
          <div className="mb-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-lg bg-white/5 px-2.5 py-1 font-medium text-slate-300">
              {job.seniority}
            </span>
            {comp && (
              <span className="rounded-lg bg-white/5 px-2.5 py-1 font-medium text-slate-300">
                {comp}
              </span>
            )}
          </div>
          <div className="mb-4 line-clamp-2 text-xs text-slate-500">{job.tech_stack}</div>

          {isLoading ? (
            <div className="flex items-end justify-between gap-4">
              <Skeleton className="h-16 w-24" />
              <Skeleton className="h-16 flex-1" />
            </div>
          ) : (
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="text-3xl font-extrabold text-white">{total}</div>
                <div className="text-xs text-slate-400">applicants</div>
              </div>
              {total > 0 && (
                <div className="h-16 w-36">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                      <Bar dataKey="value" radius={[4, 4, 4, 4]}>
                        {chartData.map((entry) => (
                          <Cell key={entry.name} fill={chartColors[entry.name as PipelineStatus]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-white/10 bg-white/[0.02] px-6 py-3 text-xs">
          <span className="text-slate-400">
            {counts.active_pipeline} in pipeline · {counts.pending_ceo_decision} at CEO
          </span>
          <span className="font-semibold text-indigo-300 transition group-hover:translate-x-1">
            Open →
          </span>
        </div>
      </motion.div>
    </Link>
  );
}

function StatTile({
  label,
  value,
  icon,
  accent,
  loading,
}: {
  label: string;
  value: number;
  icon: string;
  accent: string;
  loading: boolean;
}) {
  const animated = useCountUp(loading ? 0 : value);
  return (
    <Card className="relative overflow-hidden p-5">
      <div className={`absolute -right-6 -top-6 h-24 w-24 rounded-full blur-3xl ${accent}`} />
      <div className="relative">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-white/5 text-xl">
          {icon}
        </div>
        {loading ? (
          <Skeleton className="h-9 w-16" />
        ) : (
          <div className="text-4xl font-extrabold tracking-tight text-white">{animated}</div>
        )}
        <div className="mt-1 text-sm text-slate-400">{label}</div>
      </div>
    </Card>
  );
}

function NewJobModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [techStack, setTechStack] = useState('');
  const [seniority, setSeniority] = useState('');
  const [compMin, setCompMin] = useState('');
  const [compMax, setCompMax] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      jobsApi.createJob({
        title: title.trim(),
        tech_stack: techStack.trim(),
        seniority: seniority.trim(),
        compensation_min: compMin ? Number(compMin) : null,
        compensation_max: compMax ? Number(compMax) : null,
      }),
    onSuccess: (job) => {
      toast.success(`Job "${job.title}" created`);
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      onClose();
      setTitle('');
      setTechStack('');
      setSeniority('');
      setCompMin('');
      setCompMax('');
      navigate(`/jobs/${job.id}`);
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    mutation.mutate();
  };

  return (
    <Modal open={open} onClose={onClose} title="Create new job" subtitle="Define the role — AI can draft the rest.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={labelClass}>Job title *</label>
          <input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior Backend Engineer" className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Tech stack *</label>
          <textarea required rows={3} value={techStack} onChange={(e) => setTechStack(e.target.value)} placeholder="Python, FastAPI, PostgreSQL, Docker, AWS…" className={inputClass} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Seniority *</label>
            <input required value={seniority} onChange={(e) => setSeniority(e.target.value)} placeholder="Senior" className={inputClass} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelClass}>Comp min</label>
              <input type="number" min={0} value={compMin} onChange={(e) => setCompMin(e.target.value)} placeholder="120000" className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Comp max</label>
              <input type="number" min={0} value={compMax} onChange={(e) => setCompMax(e.target.value)} placeholder="180000" className={inputClass} />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Create job
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function DashboardPage() {
  const { user, hasRole } = useAuth();
  const [newJobOpen, setNewJobOpen] = useState(false);

  const { data: jobs, isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: jobsApi.listJobs,
  });

  const stats = useMemo(() => {
    return {
      totalJobs: jobs?.length ?? 0,
      openJobs: jobs?.filter((j) => j.status === 'posted').length ?? 0,
      draftJobs: jobs?.filter((j) => j.status === 'draft').length ?? 0,
    };
  }, [jobs]);

  return (
    <PageShell wide>
      <PageHeader
        title={`Welcome back, ${user?.full_name?.split(' ')[0] ?? 'there'} 👋`}
        subtitle="Here's what's happening across your hiring pipeline."
        actions={
          hasRole('hr') && (
            <Button onClick={() => setNewJobOpen(true)}>＋ New job</Button>
          )
        }
      />

      <Stagger>
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StaggerItem>
            <StatTile label="Total jobs" value={stats.totalJobs} icon="💼" accent="bg-indigo-500/30" loading={isLoading} />
          </StaggerItem>
          <StaggerItem>
            <StatTile label="Posted & hiring" value={stats.openJobs} icon="🚀" accent="bg-emerald-500/30" loading={isLoading} />
          </StaggerItem>
          <StaggerItem>
            <StatTile label="Drafts in progress" value={stats.draftJobs} icon="📝" accent="bg-amber-500/30" loading={isLoading} />
          </StaggerItem>
        </div>
      </Stagger>

      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Jobs</h2>
        {!isLoading && jobs && jobs.length > 0 && (
          <span className="text-sm text-slate-400">{jobs.length} total</span>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="p-6">
              <Skeleton className="mb-3 h-6 w-3/4" />
              <Skeleton className="mb-4 h-4 w-1/2" />
              <div className="flex items-end justify-between">
                <Skeleton className="h-10 w-12" />
                <Skeleton className="h-16 w-36" />
              </div>
            </Card>
          ))}
        </div>
      ) : jobs && jobs.length > 0 ? (
        <Stagger>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {jobs.map((job) => (
              <StaggerItem key={job.id}>
                <JobCard job={job} />
              </StaggerItem>
            ))}
          </div>
        </Stagger>
      ) : (
        <EmptyState
          icon="💼"
          title="No jobs yet"
          hint="Create your first job and let AI draft the description, the application form, and the LinkedIn post."
          action={hasRole('hr') ? <Button onClick={() => setNewJobOpen(true)}>＋ Create job</Button> : undefined}
        />
      )}

      <NewJobModal open={newJobOpen} onClose={() => setNewJobOpen(false)} />
    </PageShell>
  );
}
