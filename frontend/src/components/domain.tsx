import { useEffect, useState, type ReactNode } from 'react'
import type { EpisodeState, GpuInfo, Job, JobActivity } from '../api/types'
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

const PERSIAN = /[؀-ۿ]/

/** The one line to show for an error text. The server writes a Persian first line (what to do) followed by English technical
 *  lines; the English UI shows the first English line instead (when there is one). */
export function errorHeadline(text: string, lang: 'fa' | 'en'): string {
  const lines = text.split('\n')
  if (lang === 'en' && PERSIAN.test(lines[0])) {
    const english = lines.slice(1).find((l) => l.trim() !== '' && !PERSIAN.test(l))
    if (english) return english
  }
  return lines[0]
}

/** An error text that may be a long technical trace: show a short first line and keep the rest behind "technical details". */
export function ErrorText({ text }: { text: string }) {
  const { t, lang } = useI18n()
  const first = errorHeadline(text, lang)
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

/** The text of a job's activity in the active language ('' when there is none). */
export function activityText(a: JobActivity | undefined | null, field: 'title' | 'for' | 'line' | 'device', lang: 'fa' | 'en'): string {
  if (!a) return ''
  const v = (a as unknown as Record<string, unknown>)[`${field}_${lang}`]
  return typeof v === 'string' ? v : ''
}

/** A job's title in the active language: the activity title (what this step is) or else the title of its kind. */
export function useJobTitle() {
  const { tr, lang } = useI18n()
  return (j: Pick<Job, 'kind' | 'title' | 'activity'>): string => activityText(j.activity, 'title', lang) || tr('job.kind.' + j.kind, j.title || j.kind)
}

const DEVICE_TONE: Record<string, Tone> = { gpu: 'ok', mixed: 'warn', cpu: 'warn', net: 'info' }

/** The "model" and "device" chips of a job (nothing when the job reports neither). */
export function JobChips({ job }: { job: Job }) {
  const { t, lang } = useI18n()
  const a = job.activity
  const device = activityText(a, 'device', lang)
  if (!a || (!a.model && !device)) return null
  const tone: Tone = a.warn ? 'warn' : DEVICE_TONE[a.device] ?? 'neutral'
  return (
    <div className="row" style={{ gap: '0.4rem' }}>
      {a.model && (
        <Badge title={t('job.model')}>
          <span className="muted">{t('job.model')}:</span> <span className="ltr mono">{a.model}</span>
        </Badge>
      )}
      {device && <Badge tone={tone} title={t('job.device')}>{device}</Badge>}
    </div>
  )
}

/** Progress of one background job: title, what it is for, model/device chips, live line, bar, GPU wait reason, ETA (estimate, elapsed, time left), error. */
export function JobView({ job, offline, onCancel, compact, extra }: { job: Job; offline?: boolean; onCancel?: () => void; compact?: boolean; extra?: ReactNode }) {
  const { t, f, lang } = useI18n()
  const jobTitle = useJobTitle()
  const title = jobTitle(job)
  const active = job.status === 'queued' || job.status === 'running'
  const now = useNow(job.status === 'running')
  const elapsed = job.started_at && job.status === 'running' ? Math.max(0, (now - new Date(job.started_at).getTime()) / 1000) : job.duration_sec
  const indeterminate = job.status === 'queued' || (job.status === 'running' && job.progress <= 0)
  const forText = activityText(job.activity, 'for', lang)
  const line = activityText(job.activity, 'line', lang)
  const eta = job.activity?.eta_sec
  const waitingGpu = job.activity?.phase === 'waiting_gpu'
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
      {active && forText && (
        <div className="small">
          <span className="muted">{t('job.for')}:</span> <bdi>{forText}</bdi>
        </div>
      )}
      <JobChips job={job} />
      {active && line && !waitingGpu && <div className="small strong" dir="auto">{line}</div>}
      {active && <Progress value={job.progress} indeterminate={indeterminate} label={title} />}
      {active && job.status === 'running' && <div className="small muted">{f.percent(job.progress)}</div>}
      {job.progress_text && active && job.progress_text !== line && <div className="small">{job.progress_text}</div>}
      {active && (job.waiting_reason || waitingGpu) && (
        <Notice tone="warn" icon="clock">
          {waitingGpu && line ? `${t('job.waiting')}: ${line}` : job.waiting_reason ? `${t('job.waiting')}: ${job.waiting_reason}` : t('job.waiting_gpu')}
        </Notice>
      )}
      {active && (job.estimated_sec || elapsed || eta) ? (
        <div className="small muted">
          {[
            job.estimated_sec ? `${t('job.estimate')}: ${f.duration(job.estimated_sec)}` : '',
            elapsed ? `${t('job.elapsed')}: ${f.duration(elapsed)}` : '',
            eta ? t('job.eta_left', { t: f.duration(eta) }) : '',
          ].filter(Boolean).join(' · ')}
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
