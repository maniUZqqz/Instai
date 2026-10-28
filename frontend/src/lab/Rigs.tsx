import { useState } from 'react'
import { api } from '../api/client'
import { JobView } from '../components/domain'
import { useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Notice, PageHead, SelectField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { CharacterLite, MotionInfo, Rig, RigPart } from './api'
import { fileToBase64, PageCharacterPicker } from './shared'
import { useL } from './useL'
import './lab.css'

const MOUTHS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X']
type Edit = { pivot?: [number, number]; pos?: [number, number]; z?: number }

function PartsEditor({ rig, onSaved }: { rig: Rig; onSaved: () => void }) {
  const { s } = useL()
  const act = useAction()
  const [edits, setEdits] = useState<Record<string, Edit>>({})
  const names = Object.keys(rig.parts).sort((a, b) => rig.parts[a].z - rig.parts[b].z || a.localeCompare(b))
  const set = (name: string, p: RigPart, field: 'pivot' | 'pos' | 'z', idx: number, value: number) => {
    setEdits((e) => {
      const cur = e[name] ?? {}
      if (field === 'z') return { ...e, [name]: { ...cur, z: value } }
      const base = (cur[field] ?? p[field]) as [number, number]
      const next: [number, number] = idx === 0 ? [value, base[1]] : [base[0], value]
      return { ...e, [name]: { ...cur, [field]: next } }
    })
  }
  const dirty = Object.keys(edits).length > 0
  const save = () =>
    act.run(async () => {
      await api.patch(`/rigs/${rig.id}`, { parts: edits })
      setEdits({})
      onSaved()
    }, { success: s('rg.parts_saved') })
  const num = (v: number | undefined, fallback: number) => (v === undefined || Number.isNaN(v) ? fallback : v)
  return (
    <details className="lab-parts" data-testid={`parts-${rig.id}`}>
      <summary style={{ cursor: 'pointer' }}>{s('rg.edit_parts', { n: names.length })}</summary>
      <div className="stack-sm" style={{ marginBlockStart: '0.6rem' }}>
        <p className="small muted">{s('rg.edit_hint')}</p>
        <div className="table-wrap">
          <table className="table lab-parts-table">
            <thead>
              <tr>
                <th>{s('rg.col_part')}</th>
                <th>{s('rg.col_pivot')}</th>
                <th>{s('rg.col_pos')}</th>
                <th>{s('rg.col_z')}</th>
              </tr>
            </thead>
            <tbody>
              {names.map((n) => {
                const p = rig.parts[n]
                const e = edits[n] ?? {}
                const pivot = (e.pivot ?? p.pivot) as [number, number]
                const pos = (e.pos ?? p.pos) as [number, number]
                const z = e.z ?? p.z
                return (
                  <tr key={n} className={edits[n] ? 'lab-dirty' : undefined}>
                    <td>
                      <div className="row nw">
                        {p.url && <img className="lab-thumb" src={p.url} alt="" loading="lazy" />}
                        <div>
                          <div className="ltr strong small">{n}</div>
                          <div className="small muted ltr">{p.parent ? `↳ ${p.parent}` : s('rg.root')}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="lab-pair">
                        <input type="number" className="ltr" aria-label={`${n} ${s('rg.pivot')} x`} value={pivot[0]} step={1} onChange={(ev) => set(n, p, 'pivot', 0, num(ev.target.valueAsNumber, pivot[0]))} />
                        <input type="number" className="ltr" aria-label={`${n} ${s('rg.pivot')} y`} value={pivot[1]} step={1} onChange={(ev) => set(n, p, 'pivot', 1, num(ev.target.valueAsNumber, pivot[1]))} />
                      </div>
                    </td>
                    <td>
                      <div className="lab-pair">
                        <input type="number" className="ltr" aria-label={`${n} ${s('rg.pos')} x`} value={pos[0]} step={1} onChange={(ev) => set(n, p, 'pos', 0, num(ev.target.valueAsNumber, pos[0]))} />
                        <input type="number" className="ltr" aria-label={`${n} ${s('rg.pos')} y`} value={pos[1]} step={1} onChange={(ev) => set(n, p, 'pos', 1, num(ev.target.valueAsNumber, pos[1]))} />
                      </div>
                    </td>
                    <td>
                      <input type="number" className="ltr lab-z" aria-label={`${n} z`} value={z} step={1} onChange={(ev) => set(n, p, 'z', 0, num(ev.target.valueAsNumber, z))} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save} data-testid={`parts-save-${rig.id}`}>{s('rg.save_parts')}</Button>
          {dirty && <Button variant="ghost" onClick={() => setEdits({})}>{s('rg.discard')}</Button>}
        </div>
      </div>
    </details>
  )
}

function Completeness({ rig }: { rig: Rig }) {
  const { s, f } = useL()
  const c = rig.completeness
  if (!c) return null
  const have = new Set(c.mouth_shapes)
  const done = MOUTHS.filter((m) => have.has(m)).length
  return (
    <div className="stack-sm" data-testid={`completeness-${rig.id}`}>
      <div className="row">
        <span className="small muted">{s('rg.mouths')}:</span>
        <Badge tone={done === MOUTHS.length ? 'ok' : 'warn'}><span data-testid={`mouth-count-${rig.id}`}>{f.num(done)} / {f.num(MOUTHS.length)}</span></Badge>
        <ul className="chips lab-mouths" aria-label={s('rg.mouths')}>
          {MOUTHS.map((m) => (
            <li key={m} className={'chip ltr ' + (have.has(m) ? 'lab-chip-ok' : 'lab-chip-missing')} title={have.has(m) ? s('rg.mouth_present') : s('rg.mouth_missing')}>
              {m}
              <span className="sr-only"> {have.has(m) ? s('rg.mouth_present') : s('rg.mouth_missing')}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="row">
        <Badge tone={c.has_arms ? 'ok' : 'neutral'}>{c.has_arms ? s('rg.has_arms') : s('rg.no_arms')}</Badge>
        <Badge tone={c.has_legs ? 'ok' : 'neutral'}>{c.has_legs ? s('rg.has_legs') : s('rg.no_legs')}</Badge>
        <Badge tone={c.has_blink ? 'ok' : 'neutral'}>{c.has_blink ? s('rg.has_blink') : s('rg.no_blink')}</Badge>
        <span className="small muted">{s('rg.n_parts', { n: c.parts })}</span>
      </div>
      {!c.ok && <Notice tone="warn">{s('rg.incomplete')}</Notice>}
    </div>
  )
}

function RigCard({ rig, motions, onChanged }: { rig: Rig; motions: MotionInfo[]; onChanged: () => void }) {
  const { s, f } = useL()
  const confirm = useConfirm()
  const act = useAction()
  const [motion, setMotion] = useState('')
  const preview = useJobRunner<{ url: string; asset_id: number }>()
  const parts = Object.entries(rig.parts).sort((a, b) => a[1].z - b[1].z)
  const toggle = () =>
    act.run(async () => {
      await api.patch(`/rigs/${rig.id}`, { approved: !rig.approved })
      onChanged()
    }, { success: rig.approved ? s('rg.unapproved') : s('rg.approved_done') })
  const remove = async () => {
    if (!(await confirm({ title: s('rg.delete'), message: s('rg.delete_confirm', { name: rig.name }), confirmLabel: s('rg.delete'), danger: true }))) return
    await act.run(async () => {
      await api.del(`/rigs/${rig.id}`)
      onChanged()
    }, { success: s('rg.deleted') })
  }
  const runPreview = () => preview.start(() => api.post(`/rigs/${rig.id}/preview`, motion ? { motion } : {}))
  const res = preview.result
  return (
    <section className="card stack" data-testid={`rig-${rig.id}`} aria-label={rig.name}>
      <div className="row between">
        <div className="row">
          <h3 style={{ fontSize: '1.05rem' }}>{rig.name || `v${rig.version}`}</h3>
          <Badge tone="info">v{rig.version}</Badge>
          <Badge>{s(`rg.src_${rig.source}` as 'rg.src_demo')}</Badge>
          {rig.approved ? <Badge tone="ok">{s('rg.approved')}</Badge> : <Badge>{s('rg.draft')}</Badge>}
        </div>
        <span className="small muted">{f.ago(rig.created_at)}</span>
      </div>
      <Completeness rig={rig} />
      <ul className="lab-thumbs" aria-label={s('rg.parts')}>
        {parts.map(([n, p]) => (
          <li key={n} title={n}>
            {p.url ? <img src={p.url} alt={n} loading="lazy" /> : <span className="small">{n}</span>}
            <span className="small muted ltr lab-thumb-name">{n}</span>
          </li>
        ))}
      </ul>
      <PartsEditor rig={rig} onSaved={onChanged} />
      <hr className="divider" />
      <div className="row">
        <Button variant={rig.approved ? 'default' : 'primary'} icon="check" busy={act.busy} onClick={toggle} data-testid={`rig-approve-${rig.id}`}>
          {rig.approved ? s('rg.unapprove') : s('rg.approve')}
        </Button>
        <Button variant="danger" icon="trash" busy={act.busy} onClick={remove}>{s('rg.delete')}</Button>
      </div>
      <div className="stack-sm">
        <div className="row nw">
          <div className="grow">
            <SelectField
              label={s('rg.preview_motion')}
              value={motion}
              onChange={setMotion}
              options={[{ value: '', label: s('rg.motion_default') }, ...motions.map((m) => ({ value: m.name, label: `${m.name} (${f.duration(m.duration)})` }))]}
            />
          </div>
          <Button icon="play" busy={preview.busy} onClick={runPreview} data-testid={`rig-preview-${rig.id}`}>{s('rg.preview')}</Button>
        </div>
        {preview.job && preview.busy && <JobView job={preview.job} offline={preview.offline} compact />}
        {preview.failed && preview.job && <Notice tone="err">{preview.job.error || s('rg.preview_failed')}</Notice>}
        {res?.url && (
          <div className="video-box" data-testid={`rig-video-${rig.id}`}>
            <video controls playsInline src={res.url} aria-label={s('rg.preview_video')} style={{ maxWidth: '100%', maxHeight: 360 }} />
          </div>
        )}
      </div>
    </section>
  )
}

function CreateCard({ characterId, sheets, onCreated }: { characterId: number; sheets: { id: number; label: string }[]; onCreated: () => void }) {
  const { s } = useL()
  const act = useAction()
  const [sheet, setSheet] = useState('')
  const fromSheet = useJobRunner<{ rig_id?: number }>({ onSucceeded: () => onCreated() })
  const create = (body: Record<string, unknown>, success: string) =>
    act.run(async () => {
      await api.post(`/characters/${characterId}/rigs`, body)
      onCreated()
    }, { success })
  const upload = async (file: File | null, key: 'zip_base64' | 'psd_base64', source: 'upload' | 'psd', input: HTMLInputElement) => {
    if (!file) return
    const b64 = await fileToBase64(file)
    await create({ source, [key]: b64, name: file.name.replace(/\.[^.]+$/, '') }, s('rg.created'))
    input.value = ''
  }
  const psdMissing = /psd/i.test(act.error ?? '')
  return (
    <Card title={s('rg.create')}>
      <div className="stack">
        <p className="muted small">{s('rg.create_intro')}</p>
        <div className="grid-2">
          <section className="card flat stack-sm" aria-label={s('rg.demo')}>
            <h3 style={{ fontSize: '1rem' }}>{s('rg.demo')}</h3>
            <p className="small muted">{s('rg.demo_hint')}</p>
            <div><Button variant="primary" icon="plus" busy={act.busy} onClick={() => create({ source: 'demo' }, s('rg.created'))} data-testid="rig-create-demo">{s('rg.demo_btn')}</Button></div>
          </section>
          <section className="card flat stack-sm" aria-label={s('rg.zip')}>
            <h3 style={{ fontSize: '1rem' }}>{s('rg.zip')}</h3>
            <p className="small muted">{s('rg.zip_hint')}</p>
            <label className="btn" style={{ cursor: 'pointer' }}>
              {s('rg.zip_btn')}
              <input type="file" accept=".zip,application/zip" className="sr-only" data-testid="rig-zip-input" aria-label={s('rg.zip_btn')} onChange={(e) => upload(e.target.files?.[0] ?? null, 'zip_base64', 'upload', e.target)} />
            </label>
          </section>
          <section className="card flat stack-sm" aria-label={s('rg.psd')}>
            <h3 style={{ fontSize: '1rem' }}>{s('rg.psd')}</h3>
            <p className="small muted">{s('rg.psd_hint')}</p>
            <label className="btn" style={{ cursor: 'pointer' }}>
              {s('rg.psd_btn')}
              <input type="file" accept=".psd" className="sr-only" data-testid="rig-psd-input" aria-label={s('rg.psd_btn')} onChange={(e) => upload(e.target.files?.[0] ?? null, 'psd_base64', 'psd', e.target)} />
            </label>
            {psdMissing && <Notice tone="warn">{s('rg.psd_missing')}</Notice>}
          </section>
          <section className="card flat stack-sm" aria-label={s('rg.sheet')}>
            <h3 style={{ fontSize: '1rem' }}>{s('rg.sheet')}</h3>
            <p className="small muted">{s('rg.sheet_hint')}</p>
            <SelectField label={s('rg.sheet_pick')} value={sheet} onChange={setSheet} options={[{ value: '', label: s('rg.sheet_auto') }, ...sheets.map((x) => ({ value: String(x.id), label: x.label }))]} />
            <div>
              <Button icon="spark" busy={fromSheet.busy} onClick={() => fromSheet.start(() => api.post(`/characters/${characterId}/rigs`, sheet ? { source: 'sheet', sheet_asset: Number(sheet) } : { source: 'sheet' }))} data-testid="rig-from-sheet">
                {s('rg.sheet_btn')}
              </Button>
            </div>
            {fromSheet.job && fromSheet.busy && <JobView job={fromSheet.job} offline={fromSheet.offline} compact />}
            {fromSheet.failed && fromSheet.job && <Notice tone="err">{fromSheet.job.error || s('rg.sheet_failed')}</Notice>}
          </section>
        </div>
        {act.error && !psdMissing && <Notice tone="err">{act.error}</Notice>}
      </div>
    </Card>
  )
}

function RigsSection({ characterId, name }: { characterId: number; name: string }) {
  const { s } = useL()
  const q = useQuery<Rig[]>(`/characters/${characterId}/rigs`)
  const motions = useQuery<MotionInfo[]>('/puppet/motions')
  const detail = useQuery<CharacterLite>(`/characters/${characterId}`)
  const sheets = (detail.data?.references ?? []).filter((r) => r.kind === 'sheet' && r.asset).map((r) => ({ id: r.asset as number, label: r.label || `#${r.asset}` }))
  return (
    <>
      <CreateCard characterId={characterId} sheets={sheets} onCreated={q.reload} />
      <Async q={q} skeleton={<CardSkeletons n={1} />}>
        {(rigs) =>
          rigs.length === 0 ? (
            <Empty icon="users" title={s('rg.empty', { name })} text={s('rg.empty_text')} />
          ) : (
            <div className="stack-lg">
              {rigs.map((r) => (
                <RigCard key={r.id} rig={r} motions={motions.data ?? []} onChanged={q.reload} />
              ))}
            </div>
          )
        }
      </Async>
    </>
  )
}

export default function Rigs() {
  const { s } = useL()
  useTitle(s('rg.title'))
  return (
    <div className="stack-lg">
      <PageHead title={s('rg.title')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('rg.title') }]} />
      <p className="muted">{s('rg.intro')}</p>
      <PageCharacterPicker>{(p) => <RigsSection characterId={p.character!.id} name={p.character!.name} />}</PageCharacterPicker>
    </div>
  )
}
