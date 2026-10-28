import { useState } from 'react'
import { api } from '../api/client'
import { Modal, useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Notice, PageHead, Progress, SwitchField, TextField } from '../components/ui'
import { useAction, useQuery, useTitle } from '../hooks'
import type { Device, LanStatus, PairingInfo, RemoteTaskRow, WorkerRow, WorkersOverview } from './api'
import { CopyButton, useTicker } from './shared'
import { useS } from './useS'
import './studio.css'

function VramMeter({ total, free }: { total: number; free: number }) {
  const { s, f } = useS()
  if (!total) return <span className="small muted">{s('wk.vram_unknown')}</span>
  const used = Math.max(0, total - free)
  const frac = total ? used / total : 0
  return (
    <div className="stack-sm">
      <div className={'gpu-bar' + (frac > 0.85 ? ' hot' : '')} role="img" aria-label={`${s('wk.vram')}: ${f.mb(free)} ${s('wk.free')} / ${f.mb(total)}`}>
        <i style={{ width: frac * 100 + '%' }} />
      </div>
      <div className="small muted">
        {s('wk.vram')}: {f.mb(free)} {s('wk.free')} / {f.mb(total)}
      </div>
    </div>
  )
}

function Caps({ caps }: { caps: string[] }) {
  const { s } = useS()
  if (caps.length === 0) return <span className="small muted">{s('wk.no_caps')}</span>
  const shown = caps.slice(0, 6)
  const rest = caps.slice(6)
  return (
    <div className="stack-sm">
      <ul className="chips studio-caps" aria-label={s('wk.caps')}>
        {shown.map((c) => (
          <li key={c} className="chip ltr small">{c}</li>
        ))}
      </ul>
      {rest.length > 0 && (
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>{s('wk.more_caps', { n: rest.length })}</summary>
          <ul className="chips studio-caps">
            {rest.map((c) => (
              <li key={c} className="chip ltr small">{c}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function Speeds({ speed }: { speed: Record<string, { avg: number; n: number }> }) {
  const { s, f } = useS()
  const rows = Object.entries(speed || {})
  if (rows.length === 0) return <span className="small muted">{s('wk.no_speed')}</span>
  return (
    <ul className="studio-speeds small" aria-label={s('wk.speeds')}>
      {rows.map(([k, v]) => (
        <li key={k}>
          <span className="ltr">{k}</span>: <strong>{f.duration(v.avg)}</strong> <span className="muted">({s('wk.runs', { n: v.n })})</span>
        </li>
      ))}
    </ul>
  )
}

function BenchSummary({ worker }: { worker: WorkerRow }) {
  const { s, f } = useS()
  const b = worker.measured?.bench
  if (!b) return null
  return (
    <details className="small">
      <summary style={{ cursor: 'pointer' }}>{s('wk.bench_report', { when: f.ago(b.at) })}</summary>
      <ul className="studio-speeds">
        {b.image && (
          <li>
            {s('wk.bench_image')}: {s('wk.bench_cold')} <strong>{f.duration(b.image.cold)}</strong>, {s('wk.bench_warm')} <strong>{f.duration(b.image.warm)}</strong>
          </li>
        )}
        {Object.entries(b.tts ?? {}).map(([eng, r]) => (
          <li key={eng}>
            {s('wk.bench_tts')} <span className="ltr">{eng}</span>: <strong>{f.duration(r.seconds)}</strong> ({f.duration(r.audio_seconds)} {s('wk.bench_audio')})
          </li>
        ))}
        {Object.entries(b.skipped ?? {}).map(([k, why]) => (
          <li key={k} className="muted">
            <span className="ltr">{k}</span>: {why}
          </li>
        ))}
      </ul>
    </details>
  )
}

function DeviceCard({ d, w, tasks, onChanged }: { d: Device; w?: WorkerRow; tasks: RemoteTaskRow[]; onChanged: () => void }) {
  const { s, f } = useS()
  const confirm = useConfirm()
  const act = useAction()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(d.name)
  const bench = w ? tasks.find((t) => t.kind === 'bench.node' && t.worker === d.name && (t.status === 'queued' || t.status === 'running')) : undefined
  const gpuName = d.local ? d.gpu_name : w?.gpu_name

  const patch = (body: Record<string, unknown>, success?: string) =>
    act.run(async () => {
      await api.patch(`/workers/${d.id}`, body)
      onChanged()
    }, { success })
  const remove = async () => {
    if (!(await confirm({ title: s('wk.remove'), message: s('wk.remove_confirm', { name: d.name }), confirmLabel: s('wk.remove'), danger: true }))) return
    await act.run(async () => {
      await api.del(`/workers/${d.id}`)
      onChanged()
    }, { success: s('wk.removed') })
  }
  const runBench = () =>
    act.run(async () => {
      await api.post(`/workers/${d.id}/benchmark`, {})
      onChanged()
    }, { success: s('wk.bench_started') })

  return (
    <section className="card flat studio-device" aria-label={d.local ? s('wk.this_pc') : d.name} data-testid={d.local ? 'device-local' : 'device-worker'}>
      <div className="row between">
        <div className="row">
          <span className={'dot ' + (d.online ? 'ok' : 'err')} aria-hidden="true" />
          <h3 style={{ fontSize: '1.05rem' }}>{d.local ? s('wk.this_pc') : <span className="ltr">{d.name}</span>}</h3>
          <Badge tone={d.online ? 'ok' : 'err'}>{d.online ? s('wk.online') : s('wk.offline')}</Badge>
          {d.online && <Badge tone={d.busy ? 'warn' : 'neutral'}>{d.busy ? s('wk.busy') : s('wk.idle')}</Badge>}
          {!d.local && !d.enabled && <Badge tone="err">{s('wk.disabled')}</Badge>}
        </div>
        {!d.local && w && <span className="small muted">{s('wk.last_seen')}: {f.ago(w.last_seen)}</span>}
      </div>
      <div className="grid-2" style={{ marginBlockStart: '0.75rem' }}>
        <div className="stack-sm">
          <div className="small muted">{s('wk.gpu')}</div>
          <div className="strong ltr">{gpuName || <span className="muted">{s('wk.no_gpu')}</span>}</div>
          <VramMeter total={d.vram_total_mb} free={d.vram_free_mb} />
          {!d.local && w?.address && <div className="small muted">{s('wk.address')}: <span className="ltr">{w.address}</span></div>}
        </div>
        <div className="stack-sm">
          <div className="small muted">{s('wk.caps')}</div>
          <Caps caps={d.caps} />
          <div className="small muted">{s('wk.speeds')}</div>
          <Speeds speed={d.speed} />
        </div>
      </div>
      {w && <BenchSummary worker={w} />}
      {bench && (
        <div className="stack-sm" style={{ marginBlockStart: '0.5rem' }}>
          <div className="small">{s('wk.bench_running')}: {bench.progress_text || s('wk.waiting')}</div>
          <Progress value={bench.progress} indeterminate={bench.status === 'queued' || bench.progress <= 0} label={s('wk.bench_running')} />
        </div>
      )}
      {!d.local && w && (
        <div className="row" style={{ marginBlockStart: '0.75rem' }}>
          <SwitchField label={s('wk.enabled')} checked={d.enabled} disabled={act.busy} onChange={(v) => patch({ enabled: v }, v ? s('wk.enabled_on') : s('wk.enabled_off'))} />
          <Button size="sm" icon="play" busy={act.busy} disabled={!d.enabled || !d.online || !!bench} onClick={runBench}>{s('wk.bench')}</Button>
          <Button size="sm" icon="edit" onClick={() => { setName(d.name); setRenaming(true) }}>{s('wk.rename')}</Button>
          <Button size="sm" variant="danger" icon="trash" onClick={remove}>{s('wk.remove')}</Button>
        </div>
      )}
      {renaming && (
        <Modal
          title={s('wk.rename')}
          onClose={() => setRenaming(false)}
          actions={
            <>
              <Button onClick={() => setRenaming(false)}>{s('common.cancel')}</Button>
              <Button variant="primary" busy={act.busy} disabled={!name.trim()} onClick={async () => { await patch({ name: name.trim() }, s('wk.renamed')); setRenaming(false) }}>
                {s('common.save')}
              </Button>
            </>
          }
        >
          <TextField label={s('wk.name')} value={name} onChange={setName} maxLength={60} ltr />
        </Modal>
      )}
    </section>
  )
}

function PairingPanel({ pairing, lan, onClose }: { pairing: PairingInfo; lan: LanStatus; onClose: () => void }) {
  const { s, f } = useS()
  const now = useTicker(1000)
  const left = Math.max(0, Math.floor((new Date(pairing.expires_at).getTime() - now) / 1000))
  const mm = Math.floor(left / 60)
  const two = (n: number) => (n < 10 ? f.num(0) : '') + f.num(n)
  const urls = pairing.urls.length ? pairing.urls : pairing.addresses.map((a) => `http://${a}:${pairing.port}`)
  return (
    <section className="card studio-pairing" aria-label={s('wk.pair_title')} data-testid="pairing-panel">
      <div className="row between">
        <h3 style={{ fontSize: '1.05rem' }}>{s('wk.pair_title')}</h3>
        <Button size="sm" variant="ghost" iconOnly icon="close" aria-label={s('common.close')} onClick={onClose} />
      </div>
      <div className="studio-code-wrap">
        <div className="small muted">{s('wk.pair_code')}</div>
        <div className="studio-code ltr" data-testid="pairing-code" aria-label={s('wk.pair_code')}>{pairing.code}</div>
        <div className="row" style={{ justifyContent: 'center' }}>
          <CopyButton text={pairing.code} label={s('wk.copy_code')} />
          <Badge tone={left > 0 ? 'info' : 'err'}>
            {left > 0 ? s('wk.valid_for', { time: `${f.num(mm)}:${two(left % 60)}` }) : s('wk.expired')}
          </Badge>
        </div>
      </div>
      <div className="stack-sm">
        <div className="strong">{s('wk.pair_address')}</div>
        {urls.length === 0 ? (
          <Notice tone="warn">{s('wk.pair_no_address', { port: pairing.port })}</Notice>
        ) : (
          <ul className="studio-addresses">
            {urls.map((u) => {
              const short = u.replace(/^https?:\/\//, '')
              return (
                <li key={u} className="row">
                  <span className="mono ltr strong" data-testid="pairing-address">{short}</span>
                  <CopyButton text={short} label={s('wk.copy_address')} />
                </li>
              )
            })}
          </ul>
        )}
        {lan.error && <Notice tone="err">{lan.error}</Notice>}
      </div>
      <div className="stack-sm">
        <div className="strong">{s('wk.steps_title')}</div>
        <ol className="studio-steps-list" data-testid="pairing-steps">
          <li>{s('wk.step1')}</li>
          <li>{s('wk.step2')}</li>
          <li>{s('wk.step3')}</li>
          <li>{s('wk.step4')}</li>
        </ol>
        <Notice tone="info">{s('wk.firewall')}</Notice>
      </div>
    </section>
  )
}

function TasksTable({ tasks }: { tasks: RemoteTaskRow[] }) {
  const { s, f } = useS()
  if (tasks.length === 0) return <Empty icon="list" title={s('wk.tasks_empty')} text={s('wk.tasks_empty_text')} />
  const tone = (st: string) => (st === 'succeeded' ? 'ok' : st === 'failed' ? 'err' : st === 'running' ? 'info' : 'neutral')
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{s('wk.col_task')}</th>
            <th>{s('wk.col_worker')}</th>
            <th>{s('wk.col_status')}</th>
            <th>{s('wk.col_time')}</th>
            <th>{s('wk.col_when')}</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id}>
              <td>
                <div className="ltr strong">{t.kind}</div>
                <div className="small muted">#{t.id}{t.job ? ` · ${s('wk.job')} #${t.job}` : ''}</div>
              </td>
              <td className="ltr">{t.worker || '—'}</td>
              <td>
                <Badge tone={tone(t.status)}>{s(`wk.st_${t.status}` as 'wk.st_queued')}</Badge>
                {t.status === 'running' && <div className="small muted">{t.progress_text}</div>}
                {t.error && <div className="small" style={{ color: 'var(--err)' }}>{t.error.slice(0, 140)}</div>}
              </td>
              <td className="nowrap">{t.seconds != null ? f.duration(t.seconds) : '—'}</td>
              <td className="nowrap small muted">{f.ago(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Workers() {
  const { s } = useS()
  useTitle(s('wk.title'))
  const q = useQuery<WorkersOverview>('/workers', { interval: 3000 })
  const act = useAction()
  const [pairing, setPairing] = useState<PairingInfo | null>(null)

  const setLan = (enabled: boolean) =>
    act.run(async () => {
      await api.post('/workers/lan', { enabled })
      if (!enabled) setPairing(null)
      q.reload()
    }, { success: enabled ? s('wk.lan_on_done') : s('wk.lan_off_done') })
  const showCode = () =>
    act.run(async () => {
      const p = await api.post<PairingInfo>('/workers/pairing', {})
      setPairing(p)
      q.reload()
    })

  return (
    <div className="stack-lg">
      <PageHead title={s('wk.title')} crumbs={[{ label: s('studio.title'), to: '/studio' }, { label: s('wk.title') }]}>
        <Button icon="refresh" onClick={q.reload}>{s('common.refresh')}</Button>
      </PageHead>
      <p className="muted">{s('wk.intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(o) => {
          const workerByName = new Map(o.workers.map((w) => [w.name, w]))
          const remoteCount = o.devices.filter((d) => !d.local).length
          return (
            <>
              <Card title={s('wk.devices')} actions={<Badge tone={remoteCount ? 'ok' : 'neutral'}>{s('wk.n_workers', { n: remoteCount })}</Badge>}>
                <div className="stack">
                  {o.devices.map((d) => (
                    <DeviceCard key={d.name + (d.id ?? '')} d={d} w={workerByName.get(d.name)} tasks={o.recent_tasks} onChanged={q.reload} />
                  ))}
                  {remoteCount === 0 && <Notice tone="info">{s('wk.no_workers')}</Notice>}
                </div>
              </Card>

              <Card title={s('wk.lan_title')} actions={<Badge tone={o.lan.running ? 'warn' : 'neutral'}>{o.lan.running ? s('wk.lan_open', { port: o.lan.port }) : s('wk.lan_closed')}</Badge>}>
                <div className="stack">
                  <SwitchField label={s('wk.lan_switch')} hint={s('wk.lan_hint')} checked={o.lan.running} disabled={act.busy} onChange={setLan} />
                  <Notice tone="info">{s('wk.lan_explain')}</Notice>
                  {o.lan.error && <Notice tone="err">{o.lan.error}</Notice>}
                  {o.lan.running && o.lan.addresses.length > 0 && (
                    <div className="small muted">
                      {s('wk.lan_addresses')}: {o.lan.addresses.map((a) => <span key={a} className="ltr mono" style={{ marginInlineEnd: '0.6rem' }}>{a}:{o.lan.port}</span>)}
                    </div>
                  )}
                  <div className="row">
                    <Button variant="primary" icon="link" busy={act.busy} onClick={showCode}>{s('wk.show_code')}</Button>
                    <span className="small muted">{s('wk.show_code_hint')}</span>
                  </div>
                  {pairing && <PairingPanel pairing={pairing} lan={o.lan} onClose={() => setPairing(null)} />}
                </div>
              </Card>

              <Card title={s('wk.tasks')}>
                <TasksTable tasks={o.recent_tasks} />
              </Card>
            </>
          )
        }}
      </Async>
    </div>
  )
}
