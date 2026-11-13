import { useRef, useState } from 'react'
import { api } from '../api/client'
import { Modal, useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Link, Notice, PageHead, Progress, SelectField, TextField, NumberField, Segmented } from '../components/ui'
import { useAction, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { StateBadge } from './Queue'
import { CuratedLibrary } from './Curated'
import { ScheduleField } from './ScheduleField'
import type { Catalog, OpsConfig, QueueRow, When } from './types'

const HHMM = /^\d{2}:\d{2}$/

/** The saved defaults: download now, or only inside the night window; the window; an optional longest wait; how long the report keeps its data. */
function SettingsCard({ cfg, onSaved }: { cfg: OpsConfig; onSaved: () => void }) {
  const { t } = useI18n()
  const act = useAction()
  const [mode, setMode] = useState<OpsConfig['download_mode']>(cfg.download_mode)
  const [start, setStart] = useState(cfg.download_window.split('-')[0] ?? '02:00')
  const [end, setEnd] = useState(cfg.download_window.split('-')[1] ?? '07:00')
  const [wait, setWait] = useState<number | null>(cfg.max_wait_hours)
  const [keep, setKeep] = useState<number | null>(cfg.retention_days)
  const save = async () => {
    const ok = await act.run(() => api.put<OpsConfig>('/ops/config', { download_mode: mode, download_window: `${start}-${end}`, max_wait_hours: wait ?? 0, retention_days: keep ?? 30 }), { success: t('common.saved') })
    if (ok) onSaved()
  }
  return (
    <Card title={t('ops.dl.settings')}>
      <div className="stack">
        <Segmented<OpsConfig['download_mode']> label={t('ops.dl.default_mode')} value={mode} onChange={setMode} options={[{ key: 'now', label: t('ops.sched.now') }, { key: 'window', label: t('ops.dl.mode_window') }]} />
        <div className="row" style={{ gap: '1rem', alignItems: 'flex-end' }}>
          <label className="field"><span className="field-label">{t('ops.dl.win_from')}</span><input type="time" className="ltr" value={start} onChange={(e) => HHMM.test(e.target.value) && setStart(e.target.value)} /></label>
          <label className="field"><span className="field-label">{t('ops.dl.win_to')}</span><input type="time" className="ltr" value={end} onChange={(e) => HHMM.test(e.target.value) && setEnd(e.target.value)} /></label>
        </div>
        <p className="small muted">{t('ops.dl.window_note')}</p>
        <div className="grid-2">
          <NumberField label={t('ops.dl.max_wait')} hint={t('ops.dl.max_wait_hint')} value={wait} onChange={setWait} min={0} max={8760} />
          <NumberField label={t('ops.dl.retention')} hint={t('ops.dl.retention_hint')} value={keep} onChange={setKeep} min={1} max={365} />
        </div>
        <div><Button variant="primary" icon="save" busy={act.busy} onClick={save}>{t('common.save')}</Button></div>
      </div>
    </Card>
  )
}

/** Add a download: a package (models, voices, ffmpeg ...) or an Ollama model, to this PC or the second PC, now / at a time / in the night window. */
function AddCard({ cat, onAdded }: { cat: Catalog; onAdded: () => void }) {
  const { t, lang, f } = useI18n()
  const act = useAction()
  const todo = cat.packages.filter((p) => !p.offer && !p.curated && !p.complete)
  const [pkg, setPkg] = useState(todo[0]?.id ?? '')
  const [target, setTarget] = useState('local')
  const [model, setModel] = useState('')
  const when = useRef<When>({ mode: 'now' })
  const targets = cat.targets.map((x) => ({ value: x.id, label: (lang === 'en' ? x.name_en : x.name) + (x.online ? '' : ' — ' + t('ops.node.offline')) }))
  const sel = cat.packages.find((p) => p.id === pkg)
  const addPkg = async () => {
    if (!pkg) return
    await act.run(() => api.post('/downloads', { packages: [pkg], target, when: when.current }), { success: t('ops.dl.added') })
    onAdded()
  }
  const addModel = async () => {
    if (!model.trim()) return
    await act.run(() => api.post('/downloads/ollama', { model: model.trim(), when: when.current }), { success: t('ops.dl.added') })
    setModel('')
    onAdded()
  }
  return (
    <Card title={t('ops.dl.add')}>
      <div className="stack">
        <ScheduleField onChange={(w) => { when.current = w }} />
        <div className="grid-2">
          <div className="stack-sm">
            <h3 className="strong">{t('ops.dl.pack_title')}</h3>
            {todo.length === 0 ? <p className="muted small">{t('ops.dl.all_here')}</p> : (
              <>
                <SelectField label={t('ops.dl.pack')} value={pkg} onChange={setPkg}
                  options={todo.map((p) => ({ value: p.id, label: `${p.id} — ${f.bytes(p.missing_size || p.size)}` }))} />
                {sel && <p className="small muted" dir="auto">{sel.title}</p>}
                <SelectField label={t('ops.dl.target')} value={target} onChange={setTarget} options={targets} />
                <div><Button variant="primary" icon="download" busy={act.busy} disabled={!pkg} onClick={addPkg}>{t('ops.dl.go')}</Button></div>
                <p className="small muted">{t('ops.dl.optional_note')} <Link to="/models">{t('nav.models')}</Link></p>
              </>
            )}
          </div>
          <div className="stack-sm">
            <h3 className="strong">{t('ops.dl.ollama_title')}</h3>
            <TextField label={t('ops.dl.ollama_name')} hint={t('ops.dl.ollama_hint')} ltr value={model} onChange={setModel} placeholder="qwen3:8b" />
            <div className="row" style={{ gap: '0.3rem' }}>
              {cat.ollama.map((o) => (
                <button key={o.model} type="button" className="chip" onClick={() => setModel(o.model)} title={lang === 'en' ? o.en : o.fa}>
                  <span className="ltr">{o.model}</span> <span className="muted small">{f.num(o.gb, 1)} GB</span>
                </button>
              ))}
            </div>
            <div><Button variant="primary" icon="download" busy={act.busy} disabled={!model.trim()} onClick={addModel}>{t('ops.dl.go')}</Button></div>
          </div>
        </div>
      </div>
    </Card>
  )
}

function RescheduleModal({ row, onClose, onDone }: { row: QueueRow; onClose: () => void; onDone: () => void }) {
  const { t } = useI18n()
  const act = useAction()
  const when = useRef<When>({ mode: 'now' })
  const save = async () => {
    const ok = await act.run(() => api.post(`/jobs/${row.id}/schedule`, { when: when.current }), { success: t('ops.dl.rescheduled') })
    if (ok) {
      onDone()
      onClose()
    }
  }
  return (
    <Modal title={t('ops.dl.resched_title')} onClose={onClose} actions={<><Button onClick={onClose}>{t('common.cancel')}</Button><Button variant="primary" busy={act.busy} onClick={save}>{t('common.save')}</Button></>}>
      <ScheduleField onChange={(w) => { when.current = w }} initial="now" />
    </Modal>
  )
}

export default function DownloadsPage() {
  const { t, lang, f } = useI18n()
  useTitle(t('ops.dl.title'))
  const confirm = useConfirm()
  const act = useAction()
  const list = useQuery<{ jobs: QueueRow[]; config: OpsConfig }>('/downloads/queue', { interval: 4000 })
  const cat = useQuery<Catalog>('/downloads/catalog')
  const [edit, setEdit] = useState<QueueRow | null>(null)
  const reload = () => { list.reload(); cat.reload() }
  const cancel = async (r: QueueRow) => {
    if (!(await confirm({ message: t('ops.q.cancel_ask', { title: lang === 'en' ? r.title_en : r.title_fa }), confirmLabel: t('ops.q.cancel'), danger: true }))) return
    await act.run(() => api.post(`/jobs/${r.id}/cancel`, {}), { success: t('mon.cancel_sent') })
    list.reload()
  }
  const post = async (r: QueueRow, path: string, ok: string) => {
    await act.run(() => api.post(`/jobs/${r.id}/${path}`, {}), { success: ok })
    list.reload()
  }
  return (
    <div className="stack-lg">
      <PageHead title={t('ops.dl.title')}>
        <Link to="/queue" className="btn">{t('ops.dl.to_queue')}</Link>
        <Button icon="refresh" onClick={reload}>{t('common.refresh')}</Button>
      </PageHead>
      <Notice tone="info" icon="clock">{t('ops.dl.intro')}</Notice>
      <Async q={list} skeleton={<CardSkeletons n={2} />}>
        {(d) => (
          <>
            <Card title={t('ops.dl.list')} actions={<Badge tone="info">{f.num(d.jobs.length)}</Badge>}>
              {d.jobs.length === 0 ? <Empty icon="download" title={t('ops.dl.empty')} /> : (
                <div className="table-wrap">
                  <table className="table q-table">
                    <thead><tr><th>{t('ops.dl.col_what')}</th><th>{t('eps.col_state')}</th><th>{t('ops.q.col_node')}</th><th>{t('mon.col_actions')}</th></tr></thead>
                    <tbody>
                      {d.jobs.map((r) => (
                        <tr key={r.id} data-testid={'dl-' + r.id}>
                          <td dir="auto"><div className="strong">{lang === 'en' ? r.title_en : r.title_fa}</div><div className="small muted ltr">#{r.id}{r.window ? ' · ' + r.window : ''}</div></td>
                          <td>
                            <StateBadge state={r.state} />
                            <div className="small" dir="auto">{lang === 'en' ? r.state_en : r.state_fa}</div>
                            {r.state === 'running' && <Progress value={r.progress} indeterminate={r.progress <= 0} label={lang === 'en' ? r.title_en : r.title_fa} />}
                            {r.explain && r.status === 'failed' && <div className="small err-text" dir="auto">{lang === 'en' ? r.explain.what_en : r.explain.what_fa}</div>}
                          </td>
                          <td className="nowrap small">{r.target === 'local' ? t('ops.node.local_short') : r.target}</td>
                          <td>
                            <div className="row" style={{ gap: '0.25rem' }}>
                              {r.status === 'queued' && <Button size="sm" icon="play" busy={act.busy} onClick={() => post(r, 'run-now', t('ops.q.started_now'))}>{t('ops.q.run_now')}</Button>}
                              {r.status === 'queued' && <Button size="sm" icon="clock" onClick={() => setEdit(r)}>{t('ops.dl.change_time')}</Button>}
                              {r.can_cancel && <Button size="sm" variant="danger" icon="stop" busy={act.busy} onClick={() => cancel(r)}>{t('ops.q.cancel')}</Button>}
                              {r.can_retry && <Button size="sm" icon="refresh" busy={act.busy} onClick={() => post(r, 'retry', t('mon.retried'))}>{t('mon.retry')}</Button>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
            <Async q={cat} skeleton={<CardSkeletons n={2} />}>
              {(c) => (
                <>
                  <CuratedLibrary cat={c} onAdded={reload} />
                  <AddCard cat={c} onAdded={reload} />
                  <SettingsCard key={JSON.stringify(c.config)} cfg={c.config} onSaved={reload} />
                </>
              )}
            </Async>
          </>
        )}
      </Async>
      {edit && <RescheduleModal row={edit} onClose={() => setEdit(null)} onDone={reload} />}
    </div>
  )
}
