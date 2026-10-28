import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { BenchPayload, BenchResult, Hardware, HardwareItem, Job } from '../api/types'
import { JobView } from '../components/domain'
import { Icon } from '../components/Icon'
import { Async, Badge, Button, Card, CardSkeletons, CheckField, Empty, ExtLink, Notice, PageHead, type Tone } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

const STATUS_TONE: Record<string, Tone> = { ok: 'ok', warn: 'warn', missing: 'err', error: 'err' }

export default function System() {
  const { t } = useI18n()
  useTitle(t('nav.system'))
  return (
    <div className="stack-lg">
      <PageHead title={t('nav.system')} />
      <HardwareSection />
      <BenchmarkSection />
    </div>
  )
}

// ---------------------------------------------------------------- hardware and model detection
function HardwareSection() {
  const { t, f, tr } = useI18n()
  const [forced, setForced] = useState(false)
  const q = useQuery<Hardware>(forced ? '/system/hardware?refresh=1' : '/system/hardware')
  const [spinning, setSpinning] = useState(false)
  const refresh = () => {
    setSpinning(true)
    if (forced) q.reload()
    else setForced(true)
  }
  useEffect(() => {
    if (q.data) setSpinning(false)
  }, [q.data])
  return (
    <section className="stack" aria-label={t('sys.hw_title')}>
      <div className="row between">
        <h2>{t('sys.hw_title')}</h2>
        <Button icon="refresh" busy={spinning && !!q.data} onClick={refresh}>{t('sys.refresh')}</Button>
      </div>
      <p className="muted">{t('sys.hw_intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(h) => (
          <>
            <Card title={t('sys.machine')} actions={<span className="small muted">{t('sys.checked')}: {f.dateTime(h.checked_at)}</span>}>
              <div className="stack">
                <div className="row">
                  {(['ok', 'warn', 'missing', 'error'] as const).map((k) => (h.summary[k] ? <Badge key={k} tone={STATUS_TONE[k]}>{tr('sys.status_' + k)}: {f.num(h.summary[k])}</Badge> : null))}
                </div>
                <dl className="kv">
                  <dt>{t('sys.os')}</dt><dd className="ltr">{h.machine.os}</dd>
                  <dt>{t('sys.cpu')}</dt><dd className="ltr">{h.machine.cpu}</dd>
                  <dt>RAM</dt><dd>{h.machine.ram_gb ? `${f.num(h.machine.ram_gb, 1)} ${t('unit.gb')}` : t('common.unknown')}</dd>
                  <dt>GPU</dt><dd className="ltr">{h.machine.gpu ? `${h.machine.gpu}${h.machine.vram_gb ? ` · ${f.num(h.machine.vram_gb, 1)} GB` : ''}` : t('sys.no_gpu')}</dd>
                  {h.machine.driver && (<><dt>{t('mon.driver')}</dt><dd className="ltr">{h.machine.driver}</dd></>)}
                </dl>
              </div>
            </Card>
            <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 340px), 1fr))' }}>
              {h.items.map((it) => (
                <ItemCard key={it.id} it={it} />
              ))}
            </div>
          </>
        )}
      </Async>
    </section>
  )
}

function ItemCard({ it }: { it: HardwareItem }) {
  const { t, tr } = useI18n()
  const tone = STATUS_TONE[it.status] ?? 'neutral'
  const models = (it.data?.models as { name: string; size_gb: number; params?: string }[] | undefined) ?? []
  return (
    <div className="card flat stack-sm">
      <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
        <span className="strong">{it.label}</span>
        <Badge tone={tone}>
          <Icon name={it.status === 'ok' ? 'check' : it.status === 'warn' ? 'alert' : 'close'} size={14} />
          {tr('sys.status_' + it.status, it.status)}
        </Badge>
      </div>
      <div className="small">{it.detail}</div>
      {it.hint && it.status !== 'ok' && <Notice tone={it.status === 'warn' ? 'warn' : 'info'}>{it.hint}</Notice>}
      {models.length > 0 && (
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>{t('sys.models_list', { n: models.length })}</summary>
          <ul className="small ltr" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
            {models.map((m) => (
              <li key={m.name}>{m.name}{m.params ? ` · ${m.params}` : ''}{m.size_gb ? ` · ${m.size_gb} GB` : ''}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- benchmark runner and results
const STEP_KEYS = ['image', 'video', 'tts', 'llm'] as const

function BenchmarkSection() {
  const { t, f, tr } = useI18n()
  const q = useQuery<BenchPayload>('/system/benchmark')
  const [skipVideo, setSkipVideo] = useState(false)
  const runner = useJobRunner({ onFinished: () => q.reload() })
  const act = useAction()
  const running = useQuery<Job[]>('/jobs?kind=bench&status=queued,running&limit=1')
  useEffect(() => {
    const j = running.data?.[0]
    if (j && runner.jobId === null) runner.adopt(j.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running.data])
  const start = () => runner.start(() => api.post('/system/benchmark', { skip_video: skipVideo }))
  const cancel = () => runner.job && act.run(async () => { await api.post(`/jobs/${runner.job!.id}/cancel`, {}) })
  const latest = q.data?.latest ?? null
  return (
    <section className="stack" aria-label={t('sys.bench_title')}>
      <h2>{t('sys.bench_title')}</h2>
      <Card>
        <div className="stack">
          <p>{t('sys.bench_intro')}</p>
          <ul className="small" style={{ margin: 0, paddingInlineStart: '1.25rem' }}>
            <li>{t('sys.bench_time')}</li>
            <li>{t('sys.bench_needs')}</li>
            <li>{t('sys.bench_steps')}</li>
            <li>{t('sys.bench_no_fake')}</li>
          </ul>
          <CheckField label={t('sys.bench_quick')} hint={t('sys.bench_quick_hint')} checked={skipVideo} onChange={setSkipVideo} disabled={runner.busy} />
          <div className="row">
            <Button variant="primary" icon="play" busy={runner.starting} disabled={runner.busy} onClick={start}>{t('sys.bench_run')}</Button>
          </div>
          {runner.job && (runner.busy || runner.failed) && <JobView job={runner.job} offline={runner.offline} onCancel={runner.busy ? cancel : undefined} />}
        </div>
      </Card>

      <Async q={q} skeleton={<CardSkeletons n={1} />}>
        {() =>
          !latest ? (
            <Empty icon="monitor" title={t('sys.bench_empty')} text={t('sys.bench_empty_text')} />
          ) : (
            <Card
              title={t('sys.bench_results')}
              actions={
                <ExtLink href={`/api/system/benchmark/${latest.id}/report.md`} download className="btn sm">
                  <Icon name="download" />
                  {t('sys.bench_report')}
                </ExtLink>
              }
            >
              <div className="stack">
                <div className="row small muted">
                  <span>#{latest.id}</span>
                  <Badge tone={latest.status === 'done' ? 'ok' : latest.status === 'running' ? 'info' : 'warn'}>{tr('bench.status_' + latest.status, latest.status)}</Badge>
                  <span>{f.dateTime(latest.created_at)}</span>
                  {latest.options?.skip_video && <Badge>{t('sys.bench_quick_short')}</Badge>}
                </div>
                {latest.machine && (
                  <p className="small muted ltr">
                    {[latest.machine.cpu, latest.machine.ram_gb ? `${latest.machine.ram_gb} GB RAM` : '', latest.machine.gpu ? `${latest.machine.gpu} ${latest.machine.vram_gb ?? ''} GB` : 'no GPU'].filter(Boolean).join(' · ')}
                  </p>
                )}
                {latest.results.length === 0 ? (
                  <p className="muted">{t('sys.bench_no_results')}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>{t('sys.col_step')}</th>
                          <th>{t('sys.col_candidate')}</th>
                          <th>{t('sys.col_status')}</th>
                          <th>{t('sys.col_seconds')}</th>
                          <th>{t('sys.col_vram')}</th>
                          <th>{t('sys.col_notes')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortResults(latest.results).map((r, i) => (
                          <ResultRow key={i} r={r} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {(q.data?.runs.length ?? 0) > 1 && (
                  <details>
                    <summary className="small" style={{ cursor: 'pointer' }}>{t('sys.bench_older', { n: (q.data?.runs.length ?? 1) - 1 })}</summary>
                    <ul className="small" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
                      {q.data!.runs.slice(1).map((r) => (
                        <li key={r.id}>
                          #{r.id} · {f.dateTime(r.created_at)} · {tr('bench.status_' + r.status, r.status)} · <ExtLink href={`/api/system/benchmark/${r.id}/report.md`} download>{t('sys.bench_report')}</ExtLink>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </Card>
          )
        }
      </Async>
    </section>
  )
}

const sortResults = (rs: BenchResult[]) => [...rs].sort((a, b) => STEP_KEYS.indexOf(a.step as 'image') - STEP_KEYS.indexOf(b.step as 'image'))

function ResultRow({ r }: { r: BenchResult }) {
  const { t, f, tr } = useI18n()
  const tone: Tone = r.status === 'ok' ? 'ok' : r.status === 'failed' ? 'err' : 'warn'
  // only what was measured is shown; a skipped or failed step shows its reason, never a made-up number
  const details = Object.entries(r.details ?? {}).filter(([, v]) => v !== null && v !== '' && !Array.isArray(v))
  return (
    <tr>
      <td className="strong">{tr('bench.step_' + r.step, r.step)}</td>
      <td className="ltr small">{r.candidate || '—'}</td>
      <td><Badge tone={tone}>{tr('bench.res_' + r.status, r.status)}</Badge></td>
      <td className="nowrap">{r.seconds != null ? f.duration(r.seconds) : '—'}</td>
      <td className="nowrap">{r.vram_peak_mb ? f.mb(r.vram_peak_mb) : '—'}</td>
      <td className="small">
        {r.message && <div className={r.status === 'ok' ? '' : ''}>{r.status === 'skipped' ? t('sys.skipped_reason') + ': ' : ''}<span className="ltr">{r.message}</span></div>}
        {r.status === 'ok' && details.length > 0 && <div className="muted ltr">{details.map(([k, v]) => `${k}=${v}`).join(' · ')}</div>}
      </td>
    </tr>
  )
}
