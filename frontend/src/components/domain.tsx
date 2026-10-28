import { useEffect, useState, type ReactNode } from 'react'
import type { EpisodeState, GpuInfo, Job } from '../api/types'
import { useI18n } from '../i18n'
import { Badge, Button, Notice, Progress, type Tone } from './ui'

const STATE_TONE: Record<string, Tone> = {
  draft: 'neutral',
  planned: 'neutral',
  scripting: 'info',
  script_review: 'primary',
  storyboarding: 'primary',
  asset_generation: 'info',
  animation: 'info',
  assembly: 'info',
  quality_review: 'primary',
  ready_for_approval: 'warn',
  approved: 'ok',
  scheduled: 'ok',
  published: 'ok',
  failed: 'err',
  cancelled: 'neutral',
}
export const BUSY_STATES: EpisodeState[] = ['scripting', 'asset_generation', 'animation', 'assembly']

export function StateBadge({ state, label }: { state: string; label?: string }) {
  const { tr } = useI18n()
  return <Badge tone={STATE_TONE[state] ?? 'neutral'}>{tr('state.' + state, label ?? state)}</Badge>
}

export function JobStatusBadge({ status }: { status: string }) {
  const { tr } = useI18n()
  const tone: Tone = status === 'succeeded' ? 'ok' : status === 'failed' ? 'err' : status === 'running' ? 'info' : status === 'queued' ? 'warn' : 'neutral'
  return <Badge tone={tone}>{tr('job.status.' + status, status)}</Badge>
}

/** An error text that may be a long technical trace: show a short first line and keep the rest behind "technical details". */
export function ErrorText({ text }: { text: string }) {
  const { t } = useI18n()
  const first = text.split('\n')[0]
  const short = first.length > 220 ? first.slice(0, 220) + '…' : first
  const long = text.length > short.length + 2
  return (
    <div className="stack-sm">
      <div>{short}</div>
      {long && (
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>{t('job.tech_details')}</summary>
          <pre className="log-view mono" style={{ whiteSpace: 'pre-wrap', margin: '0.5rem 0 0' }}>{text}</pre>
        </details>
      )}
    </div>
  )
}

/** Re-render every second while `active` (for elapsed-time displays). */
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [active])
  return now
}

/** Progress of one background job: bar, text, GPU wait reason, ETA (estimate vs elapsed), error. */
export function JobView({ job, offline, onCancel, compact, extra }: { job: Job; offline?: boolean; onCancel?: () => void; compact?: boolean; extra?: ReactNode }) {
  const { t, f, tr } = useI18n()
  const title = tr('job.kind.' + job.kind, job.title || job.kind)
  const active = job.status === 'queued' || job.status === 'running'
  const now = useNow(job.status === 'running')
  const elapsed = job.started_at && job.status === 'running' ? Math.max(0, (now - new Date(job.started_at).getTime()) / 1000) : job.duration_sec
  const indeterminate = job.status === 'queued' || (job.status === 'running' && job.progress <= 0)
  return (
    <div className={'job' + (compact ? ' compact' : '')}>
      <span className="sr-only" role="status" aria-live="polite">
        {title}: {t(('job.status.' + job.status) as 'job.status.queued')}
        {job.status === 'running' ? ` ${f.percent(Math.round(job.progress * 10) / 10)}` : ''}
      </span>
      <div className="row between" style={{ flexWrap: 'nowrap' }}>
        <div className="grow strong">{title}</div>
        <JobStatusBadge status={job.status} />
      </div>
      {active && <Progress value={job.progress} indeterminate={indeterminate} label={title} />}
      {active && job.status === 'running' && <div className="small muted">{f.percent(job.progress)}</div>}
      {job.progress_text && active && <div className="small">{job.progress_text}</div>}
      {job.waiting_reason && active && (
        <Notice tone="warn" icon="clock">
          {t('job.waiting')}: {job.waiting_reason}
        </Notice>
      )}
      {active && (job.estimated_sec || elapsed) ? (
        <div className="small muted">
          {job.estimated_sec ? (
            <>
              {t('job.estimate')}: {f.duration(job.estimated_sec)}
              {elapsed ? ' · ' : ''}
            </>
          ) : null}
          {elapsed ? `${t('job.elapsed')}: ${f.duration(elapsed)}` : null}
        </div>
      ) : null}
      {job.status === 'succeeded' && job.duration_sec != null && !compact && (
        <div className="small muted">
          {t('job.took')}: {f.duration(job.duration_sec)}
        </div>
      )}
      {(job.status === 'failed' || job.status === 'cancelled') && (
        <Notice tone={job.status === 'failed' ? 'err' : 'info'}>{job.error ? <ErrorText text={job.error} /> : t(job.status === 'failed' ? 'job.failed' : 'job.cancelled')}</Notice>
      )}
      {offline && <Notice tone="warn">{t('job.offline')}</Notice>}
      {extra}
      {active && onCancel && (
        <div>
          <Button size="sm" variant="danger" icon="stop" onClick={onCancel} disabled={job.cancel_requested}>
            {job.cancel_requested ? t('job.cancelling') : t('job.cancel')}
          </Button>
        </div>
      )}
    </div>
  )
}

export function GpuMeter({ gpu, busyReason }: { gpu: Pick<GpuInfo, 'present' | 'name' | 'total_mb' | 'used_mb' | 'utilization'> | null; busyReason?: string }) {
  const { t, f } = useI18n()
  if (!gpu || !gpu.present) {
    return <Notice tone="warn">{t('gpu.none')}</Notice>
  }
  const total = gpu.total_mb ?? 0
  const used = gpu.used_mb ?? 0
  const frac = total ? used / total : 0
  return (
    <div className="stack-sm">
      <div className="row between">
        <span className="strong ltr">{gpu.name}</span>
        {gpu.utilization != null && (
          <span className="small muted">
            {t('gpu.util')}: {f.percent(gpu.utilization / 100)}
          </span>
        )}
      </div>
      <div className={'gpu-bar' + (frac > 0.85 ? ' hot' : '')} role="img" aria-label={`${t('gpu.vram')}: ${f.mb(used)} / ${f.mb(total)}`}>
        <i style={{ width: frac * 100 + '%' }} />
      </div>
      <div className="small muted">
        {t('gpu.vram')}: {f.mb(used)} / {f.mb(total)}
      </div>
      {busyReason && (
        <Notice tone="warn" icon="clock">
          {t('gpu.busy')}: {busyReason}
        </Notice>
      )}
    </div>
  )
}
