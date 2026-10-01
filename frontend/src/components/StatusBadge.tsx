import type { JobStatus, PipelineStatus, ScreeningDecision } from '../api/types';

const statusStyles: Record<string, string> = {
  draft: 'bg-slate-500/15 text-slate-300 border-slate-400/20',
  posted: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
  closed: 'bg-rose-500/15 text-rose-300 border-rose-400/20',
  pass: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
  fail: 'bg-rose-500/15 text-rose-300 border-rose-400/20',
  failed_at_sync: 'bg-rose-500/15 text-rose-300 border-rose-400/20',
  active_pipeline: 'bg-sky-500/15 text-sky-300 border-sky-400/20',
  pending_ceo_decision: 'bg-amber-500/15 text-amber-300 border-amber-400/20',
  closed_complete: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
  pending: 'bg-slate-500/15 text-slate-300 border-slate-400/20',
  complete: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
  sync_evaluation: 'bg-violet-500/15 text-violet-300 border-violet-400/20',
  technical_interview: 'bg-sky-500/15 text-sky-300 border-sky-400/20',
  ceo_review: 'bg-amber-500/15 text-amber-300 border-amber-400/20',
  synced: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/20',
  duplicate: 'bg-slate-500/15 text-slate-300 border-slate-400/20',
  error: 'bg-rose-500/15 text-rose-300 border-rose-400/20',
};

const labelMap: Record<string, string> = {
  failed_at_sync: 'Failed · sync',
  active_pipeline: 'In pipeline',
  pending_ceo_decision: 'CEO review',
  closed_complete: 'Closed',
  sync_evaluation: 'Sync eval',
  technical_interview: 'Interview',
  ceo_review: 'CEO review',
};

export function StatusBadge({
  value,
  dot = true,
}: {
  value: JobStatus | PipelineStatus | ScreeningDecision | string | null | undefined;
  dot?: boolean;
}) {
  if (!value) return <span className="text-slate-500">—</span>;
  const styles = statusStyles[value] ?? statusStyles.pending;
  const label = labelMap[value] ?? value.replace(/_/g, ' ');
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${styles}`}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {label}
    </span>
  );
}

export const pipelineViewOptions = [
  { id: 'all', label: 'All' },
  { id: 'active_pipeline', label: 'Passed' },
  { id: 'failed_at_sync', label: 'Failed' },
  { id: 'pending_ceo_decision', label: 'Pending CEO' },
] as const;

export type PipelineView = (typeof pipelineViewOptions)[number]['id'];
