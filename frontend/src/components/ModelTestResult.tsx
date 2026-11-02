import { createContext, useCallback, useContext, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { api } from '../api/client'
import type { Job, ModelTestResult } from '../api/types'
import { useJobRunner } from '../hooks'
import { useI18n } from '../i18n'
import { ErrorText, JobView } from './domain'
import { Icon } from './Icon'
import { Badge, Button, Notice, type Tone } from './ui'

// ---------------------------------------------------------------- only one test at a time on a page
interface Gate {
  busyId: string | null
  setBusyId: Dispatch<SetStateAction<string | null>>
}
const GateCtx = createContext<Gate>({ busyId: null, setBusyId: () => undefined })

/** Wrap the page: a running test blocks the test buttons of every other row. */
export function ModelTestGate({ children }: { children: ReactNode }) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const value = useMemo(() => ({ busyId, setBusyId }), [busyId])
  return <GateCtx.Provider value={value}>{children}</GateCtx.Provider>
}

/** One test per row: start it, follow the job, keep the last result until the row is left or the test is run again. */
export function useModelTest(id: string, llm = false) {
  const gate = useContext(GateCtx)
  const { setBusyId } = gate
  const runner = useJobRunner()
  const { start: startJob } = runner
  // between "the new job exists" and "its first poll arrived" the runner still holds the previous (finished) job
  const pending = runner.jobId !== null && runner.job?.id !== runner.jobId
  const busy = runner.busy || pending
  const job = pending ? null : runner.job
  useEffect(() => {
    setBusyId((cur) => (busy ? id : cur === id ? null : cur))
  }, [busy, id, setBusyId])
  useEffect(() => () => setBusyId((cur) => (cur === id ? null : cur)), [id, setBusyId])
  const start = useCallback(() => {
    void startJob(() => api.post<{ job: Job }>('/models/test', { id }))
  }, [startJob, id])
  const blocked = gate.busyId !== null && gate.busyId !== id
  const box = job ? <ModelTestBox job={job} offline={runner.offline} llm={llm} onAgain={start} againDisabled={blocked || busy} /> : null
  return { start, busy, blocked, hasResult: job !== null, box }
}
export type ModelTestHandle = ReturnType<typeof useModelTest>

/** The "تست" button of a row. */
export function TestButton({ test }: { test: ModelTestHandle }) {
  const { t } = useI18n()
  return (
    <Button size="sm" icon="play" busy={test.busy} disabled={test.blocked} title={test.blocked ? t('mdl.test_busy_other') : undefined} onClick={test.start}>
      {t('mdl.test')}
    </Button>
  )
}

// ---------------------------------------------------------------- the result box
const VERDICT_TONE: Record<ModelTestResult['verdict'], Tone> = { pass: 'ok', warn: 'warn', fail: 'err' }

function VerdictBadge({ verdict }: { verdict: ModelTestResult['verdict'] }) {
  const { t } = useI18n()
  const tone = VERDICT_TONE[verdict] ?? 'neutral'
  return (
    <span className={'badge ' + tone} style={{ fontSize: '1.05rem', padding: '0.2rem 0.9rem' }}>
      <Icon name={verdict === 'pass' ? 'check' : 'alert'} />
      {t(('mdl.verdict.' + verdict) as 'mdl.verdict.pass')}
    </span>
  )
}

/** A metric value with its unit, in the active language. */
function useMetricText() {
  const { t, f } = useI18n()
  return (value: number | string, unit: string): string => {
    if (typeof value !== 'number') return String(value)
    if (unit === 'MB') return f.mb(value)
    if (unit === 's') return `${f.num(value, 1)} ${t('mdl.unit.s')}`
    if (unit === 'tok/s') return `${f.num(value, 1)} ${t('mdl.unit.tok_s')}`
    if (unit === '%') return `${f.num(value, 1)}${t('mdl.unit.pct')}`
    return unit ? `${f.num(value, 1)} ${unit}` : f.num(value, Number.isInteger(value) ? 0 : 1)
  }
}

export function ModelTestBox({ job, offline, llm, onAgain, againDisabled }: { job: Job; offline?: boolean; llm?: boolean; onAgain: () => void; againDisabled?: boolean }) {
  const { t, tr, lang } = useI18n()
  const metricText = useMetricText()
  const running = job.status === 'queued' || job.status === 'running'
  const again = (
    <div>
      <Button size="sm" icon="refresh" disabled={againDisabled} onClick={onAgain}>{t('mdl.test_again')}</Button>
    </div>
  )

  if (running) {
    return (
      <div className="stack-sm">
        <JobView job={job} compact offline={offline} />
        {llm && <div className="small muted">{t('mdl.test_llm_wait')}</div>}
      </div>
    )
  }

  if (job.status !== 'succeeded') {
    return (
      <div className="test-box fail stack-sm">
        <div><VerdictBadge verdict="fail" /></div>
        <Notice tone="err">{job.error ? <ErrorText text={job.error} /> : t(job.status === 'failed' ? 'job.failed' : 'job.cancelled')}</Notice>
        {again}
      </div>
    )
  }

  const r = (job.result ?? {}) as Partial<ModelTestResult>
  if (!r.verdict) {
    return (
      <div className="test-box warn stack-sm">
        <Notice tone="warn">{t('mdl.test_no_result')}</Notice>
        {again}
      </div>
    )
  }
  const reason = (lang === 'en' ? r.reason_en : r.reason_fa) || ''
  const metrics = Array.isArray(r.metrics) ? r.metrics : []
  const dev = r.device
  const media = r.media
  return (
    <div className={'test-box ' + r.verdict + ' stack-sm'}>
      <div className="row">
        <VerdictBadge verdict={r.verdict} />
        {typeof r.seconds === 'number' && <span className="small muted">{metricText(r.seconds, 's')}</span>}
      </div>
      {reason && <div>{reason}</div>}
      {(metrics.length > 0 || dev) && (
        <div className="row" style={{ gap: '0.4rem' }}>
          {dev && dev.label && (
            <Badge tone={dev.label.includes('CPU') ? 'warn' : 'ok'} title={t('mdl.test_device')}>
              {dev.label}
              {dev.gpu_pct != null ? ` · ${t('gpu.pct_on_gpu', { n: Math.round(dev.gpu_pct) })}` : ''}
            </Badge>
          )}
          {metrics.map((m) => (
            <Badge key={m.key} title={tr('mdl.metric.' + m.key, m.key)}>
              <span className="muted">{tr('mdl.metric.' + m.key, m.key)}:</span> <bdi>{metricText(m.value, m.unit)}</bdi>
            </Badge>
          ))}
        </div>
      )}
      {r.sample ? (
        <div className="stack-sm">
          <div className="small muted">{t('mdl.test_sample')}</div>
          <blockquote className="quote-block" dir="auto">{r.sample}</blockquote>
        </div>
      ) : null}
      {media && media.url && (
        <div>
          {media.type === 'audio' && <audio controls src={media.url} style={{ width: '100%', maxWidth: 420 }} />}
          {media.type === 'image' && <img src={media.url} alt={media.name} style={{ maxWidth: 256, height: 'auto', borderRadius: 'var(--radius-sm)' }} />}
          {media.type === 'video' && <video controls src={media.url} style={{ maxWidth: '100%', width: 420, borderRadius: 'var(--radius-sm)' }} />}
        </div>
      )}
      {again}
    </div>
  )
}
