import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Job, JobLogLine, Monitor as MonitorData } from '../api/types'
import { GpuMeter, JobStatusBadge, JobView } from '../components/domain'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Link, Notice, PageHead, Segmented } from '../components/ui'
import { useAction, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

export default function Monitor() {
  const { t, f } = useI18n()
  useTitle(t('nav.monitor'))
  const q = useQuery<MonitorData>('/monitor', { interval: 2500 })
  const [logJob, setLogJob] = useState<Job | null>(null)
  const [filter, setFilter] = useState<'all' | 'failed'>('all')
  const act = useAction()
  const cancel = (j: Job) => act.run(async () => { await api.post(`/jobs/${j.id}/cancel`, {}); q.reload() }, { success: t('mon.cancel_sent') })
  const retry = (j: Job) => act.run(async () => { await api.post(`/jobs/${j.id}/retry`, {}); q.reload() }, { success: t('mon.retried') })
  return (
    <div className="stack-lg">
      <PageHead title={t('nav.monitor')}>
        <Button icon="refresh" onClick={q.reload}>{t('common.refresh')}</Button>
      </PageHead>
      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(m) => {
          const recent = m.recent.filter((j) => filter === 'all' || j.status === 'failed')
          const holder = m.active.find((j) => j.id === m.gpu_holder)
          return (
            <>
              <div className="grid-2">
                <Card title={t('mon.workers')}>
                  {m.workers.length === 0 || !m.worker_alive ? (
                    <Notice tone="err">{t('mon.worker_down')}</Notice>
                  ) : null}
                  {m.workers.length === 0 && <p className="muted" style={{ marginBlockStart: '0.5rem' }}>{t('mon.no_workers')}</p>}
                  <ul className="stack-sm" style={{ listStyle: 'none', margin: m.workers.length && !m.worker_alive ? '0.75rem 0 0' : 0, padding: 0 }}>
                    {m.workers.map((w) => (
                      <li key={w.name} className="row">
                        <span className={'dot ' + (w.alive ? 'ok' : 'err')} aria-hidden="true" />
                        <span className="strong ltr">{w.name}</span>
                        <Badge tone={w.alive ? 'ok' : 'err'}>{w.alive ? t('mon.alive') : t('mon.stopped')}</Badge>
                        <span className="small muted">{t('mon.last_seen')}: {f.ago(w.last_seen)}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
                <Card title={t('mon.gpu')}>
                  <div className="stack-sm">
                    <GpuMeter gpu={m.gpu ? { present: true, name: m.gpu.name, total_mb: m.gpu.total_mb, used_mb: m.gpu.used_mb, utilization: m.gpu.utilization } : null} busyReason={holder ? m.gpu_busy_reason || t('mon.gpu_job', { n: holder.id }) : undefined} />
                    {m.gpu && (
                      <div className="small muted">
                        {t('mon.driver')}: <span className="ltr">{m.gpu.driver}</span> · {t('mon.temp')}: {f.num(m.gpu.temperature)}°
                      </div>
                    )}
                    {m.gpu && m.gpu.processes.length > 0 && (
                      <details>
                        <summary className="small" style={{ cursor: 'pointer' }}>{t('mon.gpu_procs', { n: m.gpu.processes.length })}</summary>
                        <ul className="small" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
                          {m.gpu.processes.map((p) => (
                            <li key={p.pid} className="ltr">{p.name} — {f.mb(p.used_mb)}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    {holder && !m.gpu_busy_reason && <Notice tone="info" icon="clock">{t('mon.gpu_busy_by', { n: holder.id, title: holder.title })}</Notice>}
                  </div>
                </Card>
              </div>

              <Card title={t('mon.queue')} actions={<Badge tone={m.active.length ? 'info' : 'neutral'}>{f.num(m.active.length)}</Badge>}>
                {m.active.length === 0 ? (
                  <p className="muted">{t('dash.no_jobs')}</p>
                ) : (
                  <div className="stack-sm">
                    {m.active.map((j) => (
                      <JobView
                        key={j.id}
                        job={j}
                        onCancel={() => cancel(j)}
                        extra={
                          <div className="row small">
                            <span className="muted ltr">{j.kind}</span>
                            <JobLinks j={j} />
                            <Button size="sm" variant="ghost" icon="list" onClick={() => setLogJob(j)}>{t('mon.logs')}</Button>
                          </div>
                        }
                      />
                    ))}
                  </div>
                )}
              </Card>

              {logJob && <LogViewer job={m.active.concat(m.recent).find((j) => j.id === logJob.id) ?? logJob} onClose={() => setLogJob(null)} />}

              <Card
                title={t('mon.recent')}
                actions={
                  <Segmented
                    label={t('mon.filter')}
                    value={filter}
                    onChange={setFilter}
                    options={[{ key: 'all', label: t('mon.filter_all') }, { key: 'failed', label: t('mon.filter_failed') }]}
                  />
                }
              >
                {recent.length === 0 ? (
                  <Empty icon="list" title={t('mon.recent_empty')} />
                ) : (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>{t('mon.col_job')}</th>
                          <th>{t('eps.col_state')}</th>
                          <th>{t('mon.col_time')}</th>
                          <th>{t('mon.col_gpu')}</th>
                          <th>{t('mon.col_when')}</th>
                          <th>{t('mon.col_actions')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recent.map((j) => (
                          <tr key={j.id}>
                            <td>
                              <div className="strong">{j.title || j.kind}</div>
                              <div className="small muted ltr">{j.kind} · #{j.id}</div>
                              {j.error && <div className="small" style={{ color: 'var(--err)' }}>{j.error.split('\n')[0].slice(0, 140)}</div>}
                            </td>
                            <td><JobStatusBadge status={j.status} /></td>
                            <td className="nowrap">{f.duration(j.duration_sec)}</td>
                            <td className="nowrap">{j.gpu_seconds ? f.duration(j.gpu_seconds) : '—'}</td>
                            <td className="nowrap small muted">{f.ago(j.finished_at)}</td>
                            <td>
                              <div className="row" style={{ gap: '0.25rem' }}>
                                <Button size="sm" variant="ghost" icon="list" onClick={() => setLogJob(j)}>{t('mon.logs')}</Button>
                                {(j.status === 'failed' || j.status === 'cancelled') && <Button size="sm" icon="refresh" busy={act.busy} onClick={() => retry(j)}>{t('mon.retry')}</Button>}
                                <JobLinks j={j} />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </>
          )
        }}
      </Async>
    </div>
  )
}

function JobLinks({ j }: { j: Job }) {
  const { t } = useI18n()
  return j.episode ? <Link to={`/episodes/${j.episode}`} className="small">{t('mon.open_episode')}</Link> : j.page ? <Link to={`/pages/${j.page}`} className="small">{t('mon.open_page')}</Link> : null
}

/** Live log of one job: new lines are fetched with ?after=<last id>; scrolling follows the end only while the reader is at the end. */
function LogViewer({ job, onClose }: { job: Job; onClose: () => void }) {
  const { t, f } = useI18n()
  const [lines, setLines] = useState<JobLogLine[]>([])
  const [err, setErr] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const last = useRef(0)
  const activeRef = useRef(false)
  activeRef.current = job.status === 'queued' || job.status === 'running'

  useEffect(() => {
    setLines([])
    last.current = 0
    stick.current = true
    let alive = true
    let timer: number | undefined
    const tick = async () => {
      try {
        const more = await api.get<JobLogLine[]>(`/jobs/${job.id}/logs?after=${last.current}`)
        if (!alive) return
        setErr(false)
        if (more.length) {
          last.current = more[more.length - 1].id
          setLines((l) => [...l, ...more])
        }
      } catch {
        if (alive) setErr(true)
      }
      if (alive && (activeRef.current || last.current === 0)) timer = window.setTimeout(tick, 2000)
    }
    tick()
    return () => {
      alive = false
      if (timer) window.clearTimeout(timer)
    }
  }, [job.id])

  // one last fetch when the job ends, so the final lines are not missed
  const wasActive = useRef(false)
  useEffect(() => {
    if (wasActive.current && !activeRef.current) {
      api.get<JobLogLine[]>(`/jobs/${job.id}/logs?after=${last.current}`).then((more) => {
        if (more.length) {
          last.current = more[more.length - 1].id
          setLines((l) => [...l, ...more])
        }
      }).catch(() => undefined)
    }
    wasActive.current = activeRef.current
  }, [job.status, job.id])

  useEffect(() => {
    const el = box.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [lines])

  return (
    <Card title={<span>{t('mon.logs_of', { title: job.title || job.kind })}</span>} actions={<Button size="sm" variant="ghost" iconOnly icon="close" aria-label={t('common.close')} onClick={onClose} />}>
      <div className="stack-sm">
        {err && <Notice tone="warn">{t('job.offline')}</Notice>}
        <div
          ref={box}
          className="log-view mono"
          role="log"
          tabIndex={0}
          aria-label={t('mon.logs')}
          onScroll={(e) => {
            const el = e.currentTarget
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
          }}
        >
          {lines.length === 0 ? <span style={{ opacity: 0.7 }}>{t('mon.logs_empty')}</span> : lines.map((l) => (
            <div key={l.id} className={'log-line lvl-' + l.level}>
              <span style={{ opacity: 0.6 }}>{f.time(l.at)}</span> {l.message}
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}
