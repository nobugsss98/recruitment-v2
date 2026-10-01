import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { toast } from 'sonner';
import * as jobsApi from '../api/jobs';
import { apiErrorMessage, type GoogleFormQuestionSet, type Job } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { Button, CopyButton, inputClass } from '../components/primitives';
import { PageShell, Card, Skeleton, EmptyState } from '../components/ui';
import { StatusBadge } from '../components/StatusBadge';

type TabId = 'jd' | 'form' | 'linkedin';

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'jd', label: 'Job description', icon: '📄' },
  { id: 'form', label: 'Google Form', icon: '📝' },
  { id: 'linkedin', label: 'LinkedIn post', icon: '💼' },
];

function JdTab({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const { hasRole } = useAuth();
  const [draft, setDraft] = useState(job.jd_markdown ?? '');

  const generate = useMutation({
    mutationFn: () => jobsApi.generateJd(job.id),
    onSuccess: (updated) => {
      setDraft(updated.jd_markdown ?? '');
      queryClient.invalidateQueries({ queryKey: ['job', job.id] });
      toast.success('Job description generated with AI');
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const save = useMutation({
    mutationFn: () => jobsApi.patchJob(job.id, { jd_markdown: draft }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', job.id] });
      toast.success('Job description saved');
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-400">
          {hasRole('hr')
            ? 'Generate a tailored description with AI, then edit it to taste.'
            : 'The live job description for this role.'}
        </p>
        {hasRole('hr') && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => generate.mutate()} loading={generate.isPending}>
              ✨ Generate with AI
            </Button>
            <Button onClick={() => save.mutate()} loading={save.isPending} disabled={draft === (job.jd_markdown ?? '')}>
              💾 Save
            </Button>
          </div>
        )}
      </div>
      <textarea
        rows={18}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        readOnly={!hasRole('hr')}
        placeholder={hasRole('hr') ? 'Click “Generate with AI” to draft the description…' : 'No description yet.'}
        className={`${inputClass} font-mono text-[13px] leading-relaxed`}
      />
      {generate.isPending && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-3 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200"
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-300/40 border-t-indigo-200" />
          Drafting the perfect job description…
        </motion.div>
      )}
    </div>
  );
}

function FormTab({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const { hasRole } = useAuth();
  const [questions, setQuestions] = useState<GoogleFormQuestionSet | null>(null);

  const generateQuestions = useMutation({
    mutationFn: () => jobsApi.generateFormQuestions(job.id),
    onSuccess: (qs) => {
      setQuestions(qs);
      toast.success(`${qs.questions.length} questions generated`);
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const clone = useMutation({
    mutationFn: () => jobsApi.cloneForm(job.id, questions!),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['job', job.id] });
      toast.success(`Form cloned — ${result.questions_added} questions added`);
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const canClone = hasRole('hr') && questions && questions.questions.length > 0;

  return (
    <div className="space-y-5">
      {job.google_form_url ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-5"
        >
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-emerald-300">
            ✅ Application form is live
          </div>
          <div className="mb-3 break-all text-sm text-slate-300">{job.google_form_url}</div>
          <div className="flex flex-wrap gap-2">
            <CopyButton text={job.google_form_url} label="Copy responder link" />
            <a href={job.google_form_url} target="_blank" rel="noreferrer">
              <Button variant="secondary" size="sm">
                Open form ↗
              </Button>
            </a>
          </div>
        </motion.div>
      ) : (
        <EmptyState
          icon="📝"
          title="No application form yet"
          hint={
            hasRole('hr')
              ? 'Generate screening questions with AI, review them, then clone a live Google Form.'
              : 'HR has not created the application form for this role yet.'
          }
        />
      )}

      {hasRole('hr') && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-white">
              {job.google_form_url ? 'Re-clone with fresh questions' : 'Build the form'}
            </h3>
            <Button
              variant="secondary"
              onClick={() => generateQuestions.mutate()}
              loading={generateQuestions.isPending}
            >
              ✨ Generate questions with AI
            </Button>
          </div>

          <AnimatePresence>
            {questions && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="space-y-2 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                  {questions.questions.map((q, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="flex items-start gap-3 rounded-xl bg-white/[0.03] px-4 py-3"
                    >
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-indigo-500/20 text-xs font-bold text-indigo-300">
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-white">{q.title}</div>
                        <div className="mt-0.5 text-xs capitalize text-slate-400">
                          {q.question_type.replace(/_/g, ' ')}
                          {q.required ? ' · required' : ''}
                          {q.options.length > 0 && ` · ${q.options.length} options`}
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
                <div className="mt-4 flex justify-end">
                  <Button onClick={() => clone.mutate()} loading={clone.isPending} disabled={!canClone}>
                    📋 Clone Google Form
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function LinkedinTab({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const { hasRole } = useAuth();

  const generate = useMutation({
    mutationFn: () => jobsApi.generateLinkedinBlurb(job.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', job.id] });
      toast.success('LinkedIn blurb generated');
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  const ready = Boolean(job.jd_markdown && job.google_form_url);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-400">
          {ready
            ? 'A punchy post linking candidates to the application form.'
            : 'Generate a job description and clone the application form first — the blurb needs both.'}
        </p>
        <div className="flex gap-2">
          {job.linkedin_blurb && <CopyButton text={job.linkedin_blurb} label="Copy post" />}
          {hasRole('hr') && (
            <Button onClick={() => generate.mutate()} loading={generate.isPending} disabled={!ready}>
              ✨ {job.linkedin_blurb ? 'Regenerate' : 'Generate blurb'}
            </Button>
          )}
        </div>
      </div>
      {job.linkedin_blurb ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="whitespace-pre-wrap rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm leading-relaxed text-slate-200"
        >
          {job.linkedin_blurb}
        </motion.div>
      ) : (
        <EmptyState icon="💼" title="No LinkedIn post yet" hint="Generate one once the JD and form are ready." />
      )}
    </div>
  );
}

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabId>('jd');

  const { data: job, isLoading } = useQuery({
    queryKey: ['job', id],
    queryFn: () => jobsApi.getJob(id!),
    enabled: Boolean(id),
  });

  const setStatus = useMutation({
    mutationFn: (status: Job['status']) => jobsApi.patchJob(id!, { status }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['job', id] });
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      toast.success(`Job marked as ${updated.status}`);
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  });

  if (isLoading) {
    return (
      <PageShell>
        <Skeleton className="mb-4 h-9 w-1/2" />
        <Skeleton className="mb-8 h-4 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </PageShell>
    );
  }

  if (!job) {
    return (
      <PageShell>
        <EmptyState icon="🔍" title="Job not found" hint="This job may have been deleted." />
      </PageShell>
    );
  }

  return (
    <PageShell wide>
      <div className="mb-6">
        <Link to="/" className="text-sm text-slate-400 transition hover:text-white">
          ← All jobs
        </Link>
      </div>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <h1 className="text-3xl font-extrabold tracking-tight text-white">{job.title}</h1>
            <StatusBadge value={job.status} />
          </div>
          <p className="text-sm text-slate-400">
            {job.seniority}
            {job.compensation_min != null || job.compensation_max != null
              ? ` · $${job.compensation_min?.toLocaleString() ?? '—'} – $${job.compensation_max?.toLocaleString() ?? '—'}`
              : ''}
          </p>
          <p className="mt-1 line-clamp-2 max-w-2xl text-xs text-slate-500">{job.tech_stack}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/jobs/${job.id}/screening`}>
            <Button variant="secondary">👥 Screening</Button>
          </Link>
          {hasRole('hr') && (
            <>
              {job.status !== 'posted' && (
                <Button variant="success" size="sm" onClick={() => setStatus.mutate('posted')} loading={setStatus.isPending}>
                  🚀 Mark posted
                </Button>
              )}
              {job.status !== 'closed' && (
                <Button variant="danger" size="sm" onClick={() => setStatus.mutate('closed')} loading={setStatus.isPending}>
                  🔒 Close job
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      <div className="mb-6 flex gap-1 rounded-2xl border border-white/10 bg-surface-850/60 p-1.5">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`relative flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
              tab === t.id ? 'text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab === t.id && (
              <motion.span
                layoutId="job-tab"
                className="absolute inset-0 rounded-xl bg-gradient-to-r from-indigo-500/40 to-violet-500/30"
                transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              />
            )}
            <span className="relative">
              {t.icon} {t.label}
            </span>
          </button>
        ))}
      </div>

      <Card className="p-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22 }}
          >
            {tab === 'jd' && <JdTab job={job} />}
            {tab === 'form' && <FormTab job={job} />}
            {tab === 'linkedin' && <LinkedinTab job={job} />}
          </motion.div>
        </AnimatePresence>
      </Card>
    </PageShell>
  );
}
