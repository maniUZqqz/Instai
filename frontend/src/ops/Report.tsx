import { useMemo, useState } from 'react'
import { Async, Badge, Card, CardSkeletons, Empty, ExtLink, Notice, PageHead, Progress, Segmented, SelectField, TextField, Button } from '../components/ui'
import { useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { StateBadge, useNodeName } from './Queue'
import type { DownloadRow, ErrorGroup, KindRow, LogRow, NodeReport, ReportData, SeriesPoint, Stats } from './types'

type Preset = 'today' | '7' | '30' | 'custom'

function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** The date filter as a query string for the API (and the CSV links). */
function rangeQuery(preset: Preset, from: string, to: string): string {
  if (preset === 'today') return `from=${ymd(new Date())}&to=${ymd(new Date())}`
  if (preset === 'custom' && from) return `from=${from}&to=${to || ymd(new Date())}`
  return `days=${preset === '30' ? 30 : 7}`
}

// ---------------------------------------------------------------- small drawings (inline SVG / CSS, no chart library)

/** Online timeline: the whole bar is the chosen period (dim = offline), the bright pieces are the online stretches. */
function Timeline({ from, to, sessions, label }: { from: string; to: string; sessions: { start: string; end: string }[]; label: string }) {
  const a = new Date(from).getTime()
  const b = Math.min(new Date(to).getTime(), Date.now())
  const span = Math.max(1, new Date(to).getTime() - a)
  return (
    <div className="tl" role="img" aria-label={label} title={label}>
      {sessions.map((s, i) => {
        const x = Math.max(0, (new Date(s.start).getTime() - a) / span) * 100
        const w = Math.max(0.4, ((Math.min(new Date(s.end).getTime(), b) - Math.max(new Date(s.start).getTime(), a)) / span) * 100)
        return <i key={i} style={{ insetInlineStart: x + '%', inlineSize: w + '%' }} />
      })}
    </div>
  )
}

function Spark({ values, label, tone }: { values: (number | null)[]; label: string; tone: 'info' | 'warn' | 'ok' }) {
  const { f, lang } = useI18n()
  const pc = lang === 'fa' ? '٪' : '%'
  const real = values.filter((v): v is number => v !== null)
  if (real.length < 2) return <div className="small muted">{label}: —</div>
  const W = 220
  const H = 44
  const step = W / (values.length - 1)
  let d = ''
  values.forEach((v, i) => {
    if (v === null) return
    const y = H - 2 - (Math.min(100, Math.max(0, v)) / 100) * (H - 4)
    d += `${d && values[i - 1] !== null ? 'L' : 'M'}${(i * step).toFixed(1)} ${y.toFixed(1)} `
  })
  const last = real[real.length - 1]
  const max = Math.max(...real)
  return (
    <div className="spark">
      <div className="small row between"><span className="muted">{label}</span><span className="ltr nowrap">{f.num(last, 0)}{pc} · max {f.num(max, 0)}{pc}</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}: ${f.num(last, 0)}%`} preserveAspectRatio="none" className={'spark-svg ' + tone}>
        <line x1="0" y1={H - 2} x2={W} y2={H - 2} className="spark-base" />
        <path d={d} fill="none" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

function statText(s: Stats, f: ReturnType<typeof useI18n>['f']): string {
  return s.n ? f.duration(s.avg) : '—'
}

// ---------------------------------------------------------------- one computer

function Gauge({ label, value, text }: { label: string; value: number | null | undefined; text: string }) {
  const tone = value == null ? undefined : value >= 90 ? 'err' : value >= 75 ? 'warn' : 'ok'
  return (
    <div className="stack-sm">
      <div className="small row between"><span className="muted">{label}</span><span className="ltr nowrap">{text}</span></div>
      <Progress value={value == null ? 0 : value / 100} tone={tone} label={label} />
    </div>
  )
}

function NodeCard({ n, range }: { n: NodeReport; range: { from: string; to: string }; mainVersion: string }) {
  const { t, lang, f } = useI18n()
  const name = useNodeName()
  const c = n.current
  const pct = (used: number | null | undefined, total: number | null | undefined) => (used != null && total ? Math.round((100 * used) / total) : null)
  const vram = pct(c?.vram_used_mb, c?.vram_total_mb)
  const ram = pct(c?.ram_used_mb, c?.ram_total_mb)
  const series = (k: keyof SeriesPoint) => n.series.map((p) => p[k] as number | null)
  const j = n.jobs
  const rate = j.succeeded + j.failed > 0 ? j.succeeded / (j.succeeded + j.failed) : null
  const tlLabel = n.uptime_pct == null ? t('ops.rep.no_sessions') : t('ops.rep.uptime_n', { n: n.uptime_pct })
  return (
    <Card
      title={
        <span className="row" style={{ gap: '0.6rem' }}>
          <span className={'dot ' + (n.online ? 'ok' : 'err')} aria-hidden="true" />
          <span>{name(n)}</span>
          <Badge tone={n.online ? 'ok' : n.enabled ? 'err' : 'neutral'}>{n.online ? t('ops.node.online') : n.enabled ? t('ops.node.offline') : t('ops.node.disabled')}</Badge>
          {n.version && <span className="small muted ltr">v{n.version}</span>}
        </span>
      }
    >
      <div className="stack" data-testid={'report-node-' + n.key}>
        <div className="small muted row" style={{ gap: '1rem' }}>
          {n.gpu_name && <span className="ltr">{n.gpu_name}</span>}
          {n.host && <span className="ltr">{n.host}</span>}
          <span>{n.last_seen ? t('ops.node.last_seen', { when: f.ago(n.last_seen) }) : t('ops.node.never')}</span>
        </div>

        <section className="stack-sm" aria-label={t('ops.rep.timeline')}>
          <div className="row between"><strong>{t('ops.rep.timeline')}</strong><span className="small">{tlLabel}{n.online_minutes ? ' · ' + t('ops.rep.online_for', { d: f.duration(n.online_minutes * 60) }) : ''}</span></div>
          <Timeline from={range.from} to={range.to} sessions={n.sessions} label={tlLabel} />
          <div className="small muted row between"><span>{f.date(range.from)}</span><span>{f.date(range.to)}</span></div>
        </section>

        {c ? (
          <section className="grid-2" aria-label={t('ops.rep.resources')}>
            <div className="stack-sm">
              <Gauge label={t('ops.rep.gpu')} value={c.gpu_util} text={c.gpu_util == null ? '—' : `${f.num(c.gpu_util)}${lang === 'fa' ? '٪' : '%'}${c.gpu_temp != null ? ` · ${f.num(c.gpu_temp)}°` : ''}`} />
              <Gauge label={t('ops.rep.vram')} value={vram} text={c.vram_total_mb ? `${f.mb(c.vram_used_mb)} / ${f.mb(c.vram_total_mb)}` : '—'} />
              <Gauge label={t('ops.rep.ram')} value={ram} text={c.ram_total_mb ? `${f.mb(c.ram_used_mb)} / ${f.mb(c.ram_total_mb)}` : '—'} />
              <div className="small row between"><span className="muted">{t('ops.rep.disk')}</span><span className="ltr">{c.disk_free_gb != null ? `${f.num(c.disk_free_gb, 1)} / ${f.num(c.disk_total_gb, 0)} GB` : '—'}</span></div>
              <div className="small muted">{t('ops.rep.sample_at', { when: f.ago(c.at) })}</div>
            </div>
            <div className="stack-sm">
              <Spark values={series('gpu_util')} label={t('ops.rep.gpu')} tone="info" />
              <Spark values={series('vram_pct')} label={t('ops.rep.vram')} tone="warn" />
              <Spark values={series('ram_pct')} label={t('ops.rep.ram')} tone="ok" />
            </div>
          </section>
        ) : (
          <p className="small muted">{t('ops.rep.no_samples')}</p>
        )}

        <section className="stack-sm" aria-label={t('ops.rep.jobs')}>
          <strong>{t('ops.rep.jobs')}</strong>
          {j.total === 0 ? (
            <p className="small muted">{t('ops.rep.no_jobs')}</p>
          ) : (
            <>
              <div className="row" style={{ gap: '1.25rem' }}>
                <span>{t('ops.rep.total')}: <strong>{f.num(j.total)}</strong></span>
                <span className="ok-text">{t('ops.rep.ok')}: <strong>{f.num(j.succeeded)}</strong></span>
                <span className="err-text">{t('ops.rep.fail')}: <strong>{f.num(j.failed)}</strong></span>
                <span>{t('ops.rep.cancel')}: <strong>{f.num(j.cancelled)}</strong></span>
                {rate != null && <span>{t('ops.rep.rate')}: <strong>{f.percent(rate)}</strong></span>}
              </div>
              <div className="small muted row" style={{ gap: '1.25rem' }}>
                <span>{t('ops.rep.avg_dur')}: {statText(j.duration, f)}</span>
                <span>{t('ops.rep.avg_wait')}: {statText(j.wait, f)}</span>
                {j.wait.max != null && <span>{t('ops.rep.max_wait')}: {f.duration(j.wait.max)}</span>}
                <span>{t('ops.rep.gpu_time')}: {f.duration(j.gpu_seconds)}</span>
                {j.deferrals > 0 && <span>{t('ops.rep.waits_n', { n: j.deferrals })}</span>}
              </div>
              <KindTable rows={n.by_kind} lang={lang} />
            </>
          )}
        </section>

        {n.tasks.length > 0 && (
          <section className="stack-sm" aria-label={t('ops.rep.tasks')}>
            <strong>{t('ops.rep.tasks')}</strong>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>{t('ops.rep.col_task')}</th><th>{t('ops.rep.total')}</th><th>{t('ops.rep.ok')}</th><th>{t('ops.rep.fail')}</th><th>{t('ops.rep.cancel')}</th><th>{t('ops.rep.lost')}</th><th>{t('ops.rep.avg_dur')}</th></tr></thead>
                <tbody>
                  {n.tasks.map((k) => (
                    <tr key={k.kind}>
                      <td className="ltr">{k.kind}</td><td>{f.num(k.total)}</td><td>{f.num(k.succeeded)}</td><td>{f.num(k.failed)}</td><td>{f.num(k.cancelled)}</td><td>{f.num(k.lost)}</td><td>{statText(k.duration, f)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </Card>
  )
}

function KindTable({ rows, lang }: { rows: KindRow[]; lang: 'fa' | 'en' }) {
  const { t, f } = useI18n()
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{t('ops.rep.col_kind')}</th><th>{t('ops.rep.total')}</th><th>{t('ops.rep.ok')}</th><th>{t('ops.rep.fail')}</th><th>{t('ops.rep.cancel')}</th><th>{t('ops.rep.avg_dur')}</th><th>{t('ops.rep.avg_wait')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((k) => (
            <tr key={k.kind}>
              <td><div className="strong" dir="auto">{lang === 'en' ? k.title_en : k.title_fa}</div><div className="small muted ltr">{k.kind}</div></td>
              <td>{f.num(k.total)}</td><td>{f.num(k.succeeded)}</td><td>{f.num(k.failed)}</td><td>{f.num(k.cancelled)}</td>
              <td className="nowrap">{statText(k.duration, f)}</td><td className="nowrap">{statText(k.wait, f)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------- errors, downloads, logs

function Errors({ rows }: { rows: ErrorGroup[] }) {
  const { t, lang, f } = useI18n()
  if (rows.length === 0) return <Empty icon="check" title={t('ops.rep.no_errors')} />
  return (
    <div className="stack">
      {rows.map((g) => (
        <div key={g.code} className="card flat stack-sm" data-testid={'error-' + g.code}>
          <div className="row between">
            <span className="strong" dir="auto">{lang === 'en' ? g.what_en : g.what_fa}</span>
            <Badge tone="err">{t('ops.rep.times', { n: g.count })}</Badge>
          </div>
          <div className="small" dir="auto"><strong>{t('ops.rep.what_to_do')}:</strong> {lang === 'en' ? g.advice_en : g.advice_fa}</div>
          <div className="small muted">{t('ops.rep.last_at', { when: f.ago(g.last_at) })} · {g.kinds.slice(0, 4).map((k) => `${k.kind} ×${k.count}`).join('، ')}</div>
          {g.sample && (
            <details>
              <summary className="small" style={{ cursor: 'pointer' }}>{t('ops.rep.tech')}</summary>
              <pre className="mono small ltr" style={{ whiteSpace: 'pre-wrap' }}>{g.sample}</pre>
            </details>
          )}
        </div>
      ))}
    </div>
  )
}

function Downloads({ rows }: { rows: DownloadRow[] }) {
  const { t, lang, f } = useI18n()
  if (rows.length === 0) return <Empty icon="download" title={t('ops.rep.no_downloads')} />
  return (
    <div className="table-wrap">
      <table className="table q-table">
        <thead><tr><th>{t('ops.dl.col_what')}</th><th>{t('eps.col_state')}</th><th>{t('ops.q.col_node')}</th><th>{t('ops.rep.avg_dur')}</th><th>{t('mon.col_when')}</th></tr></thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td dir="auto">{lang === 'en' ? d.title_en : d.title_fa}<div className="small muted ltr">#{d.id}{d.window ? ' · ' + d.window : ''}</div></td>
              <td><StateBadge state={d.state} /><div className="small" dir="auto">{lang === 'en' ? d.state_en : d.state_fa}</div>
                {d.explain && <div className="small err-text" dir="auto">{lang === 'en' ? d.explain.what_en : d.explain.what_fa}</div>}</td>
              <td className="nowrap small">{d.target === 'local' ? t('ops.node.local_short') : d.target}</td>
              <td className="nowrap">{d.duration_sec != null ? f.duration(d.duration_sec) : '—'}</td>
              <td className="nowrap small muted">{f.ago(d.finished_at ?? d.started_at ?? d.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Logs({ query, nodes }: { query: string; nodes: NodeReport[] }) {
  const { t, lang, f } = useI18n()
  const name = useNodeName()
  const [q, setQ] = useState('')
  const [level, setLevel] = useState('')
  const [node, setNode] = useState('')
  const [source, setSource] = useState('all')
  const params = useMemo(() => `${query}&q=${encodeURIComponent(q)}&level=${level}&node=${encodeURIComponent(node)}&source=${source}`, [query, q, level, node, source])
  const logs = useQuery<{ rows: LogRow[]; count: number }>('/reports/logs?' + params)
  return (
    <div className="stack">
      <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        <TextField label={t('ops.rep.search')} value={q} onChange={setQ} placeholder={t('ops.rep.search_ph')} />
        <SelectField label={t('ops.rep.level')} value={level} onChange={setLevel} options={[{ value: '', label: t('ops.rep.all') }, { value: 'error', label: t('ops.rep.lv_error') }, { value: 'warning', label: t('ops.rep.lv_warning') }, { value: 'info', label: t('ops.rep.lv_info') }]} />
        <SelectField label={t('ops.rep.computer')} value={node} onChange={setNode} options={[{ value: '', label: t('ops.rep.all') }, ...nodes.map((n) => ({ value: n.key, label: name(n) }))]} />
        <SelectField label={t('ops.rep.source')} value={source} onChange={setSource} options={[{ value: 'all', label: t('ops.rep.all') }, { value: 'jobs', label: t('ops.rep.src_jobs') }, { value: 'events', label: t('ops.rep.src_events') }]} />
      </div>
      <div className="small muted">{logs.data ? t('ops.rep.found_n', { n: logs.data.count }) : ''}</div>
      <div className="log-view mono" role="log" tabIndex={0} aria-label={t('ops.rep.logs')} style={{ maxBlockSize: '22rem' }}>
        {logs.data && logs.data.rows.length === 0 && <span style={{ opacity: 0.7 }}>{t('ops.rep.no_logs')}</span>}
        {logs.data?.rows.map((r, i) => (
          <div key={i} className={'log-line lvl-' + r.level} title={r.explain ? (lang === 'en' ? r.explain.what_en : r.explain.what_fa) : undefined}>
            <span style={{ opacity: 0.6 }}>{f.dateTime(r.at)}</span>{' '}
            <span className="badge neutral">{r.node === 'local' ? t('ops.node.local_short') : r.node}</span>{' '}
            {r.source === 'job' && <span style={{ opacity: 0.75 }}>#{r.job} {lang === 'en' ? r.title_en : r.title_fa} · </span>}
            {r.source === 'event' && r.kind !== 'log' && r.kind !== 'error' ? (lang === 'en' ? r.text_en : r.text_fa) : r.message}
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- the page

const SECTIONS = ['jobs', 'nodes', 'samples', 'sessions', 'errors', 'downloads', 'logs'] as const

/** «گزارش کامپیوترهای پردازش»: when each computer was online, how it was loaded, what it did, what went wrong and why; with a date filter and CSV. */
export default function ReportPage() {
  const { t, f } = useI18n()
  useTitle(t('ops.rep.title'))
  const [preset, setPreset] = useState<Preset>('7')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const query = rangeQuery(preset, from, to)
  const q = useQuery<ReportData>('/reports/compute?' + query, { interval: 30000 })
  return (
    <div className="stack-lg">
      <PageHead title={t('ops.rep.title')}>
        <Button icon="refresh" onClick={q.reload}>{t('common.refresh')}</Button>
      </PageHead>
      <p className="muted">{t('ops.rep.intro')}</p>
      <Card>
        <div className="stack">
          <div className="row" style={{ gap: '1rem', alignItems: 'flex-end' }}>
            <Segmented<Preset> label={t('ops.rep.range')} value={preset} onChange={setPreset} options={[
              { key: 'today', label: t('ops.rep.r_today') }, { key: '7', label: t('ops.rep.r_7') }, { key: '30', label: t('ops.rep.r_30') }, { key: 'custom', label: t('ops.rep.r_custom') },
            ]} />
            {preset === 'custom' && (
              <>
                <label className="field"><span className="field-label">{t('ops.rep.from')}</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="ltr" /></label>
                <label className="field"><span className="field-label">{t('ops.rep.to')}</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="ltr" /></label>
              </>
            )}
          </div>
          <div className="row" style={{ gap: '0.4rem' }} aria-label={t('ops.rep.export')}>
            <span className="small muted">{t('ops.rep.export')}:</span>
            {SECTIONS.map((s) => (
              <ExtLink key={s} href={`/api/reports/export.csv?section=${s}&${query}`} download className="btn sm">{t('ops.rep.csv_' + s)}</ExtLink>
            ))}
          </div>
        </div>
      </Card>
      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(r) => {
          const seen = r.nodes.filter((n) => n.kind === 'worker' && n.last_seen)
          const old = seen.filter((n) => n.version && n.version !== r.versions.main)
          const unknown = seen.filter((n) => !n.version)
          const tt = r.totals
          return (
            <>
              {old.map((n) => <Notice key={n.key} tone="warn" icon="alert">{t('ops.rep.old_version', { name: n.key, v: n.version, main: r.versions.main })}</Notice>)}
              {unknown.map((n) => <Notice key={n.key} tone="warn" icon="alert">{t('ops.rep.old_unknown', { name: n.key, main: r.versions.main })}</Notice>)}
              <div className="grid-auto q-counters" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                <Stat label={t('ops.rep.total')} value={f.num(tt.jobs)} />
                <Stat label={t('ops.rep.ok')} value={f.num(tt.succeeded)} tone="ok" />
                <Stat label={t('ops.rep.fail')} value={f.num(tt.failed)} tone={tt.failed ? 'err' : undefined} />
                <Stat label={t('ops.rep.cancel')} value={f.num(tt.cancelled)} />
                <Stat label={t('ops.rep.avg_dur')} value={statText(tt.duration, f)} />
                <Stat label={t('ops.rep.avg_wait')} value={statText(tt.wait, f)} />
                <Stat label={t('ops.rep.waits')} value={f.num(tt.deferrals)} />
                <Stat label={t('ops.rep.gpu_time')} value={f.duration(tt.gpu_seconds)} />
              </div>
              {r.nodes.map((n) => <NodeCard key={n.key} n={n} range={r.range} mainVersion={r.versions.main} />)}
              <Card title={t('ops.rep.errors')}><Errors rows={r.errors} /></Card>
              <Card title={t('ops.rep.downloads')}><Downloads rows={r.downloads} /></Card>
              <Card title={t('ops.rep.logs')}><Logs query={query} nodes={r.nodes} /></Card>
            </>
          )
        }}
      </Async>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'err' }) {
  return (
    <div className={'card flat q-counter ' + (tone ?? 'neutral')}>
      <div className="q-counter-n">{value}</div>
      <div className="small muted">{label}</div>
    </div>
  )
}
