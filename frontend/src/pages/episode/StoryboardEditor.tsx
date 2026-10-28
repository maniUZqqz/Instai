import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Episode, EpisodeEstimate, PageDetail, Shot } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { Badge, Button, Card, CheckField, Notice, NumberField, SelectField, TextField, AreaField } from '../../components/ui'
import { CAMERA_MOVES, IMPLEMENTED_TECHNIQUES, useFormats } from '../../formats'
import { useAction } from '../../hooks'
import { useI18n } from '../../i18n'

interface DShot {
  key: string
  id?: number
  description: string
  image_prompt: string
  technique: string
  move: string
  intensity: number
  duration_sec: number
  narration: string
  speaker: string
  sfx: string
  transition: string
}
interface DScene {
  key: string
  id?: number
  title: string
  summary: string
  location: string
  characters: string[]
  approved: boolean
  shots: DShot[]
}

let seq = 0
const nk = () => `n${++seq}`

function fromShot(s: Shot): DShot {
  return {
    key: `s${s.id}`,
    id: s.id,
    description: s.description,
    image_prompt: s.image_prompt,
    technique: s.technique,
    move: s.camera?.move ?? 'zoom_in',
    intensity: s.camera?.intensity ?? 0.5,
    duration_sec: s.duration_sec,
    narration: s.narration,
    speaker: s.speaker,
    sfx: s.sfx,
    transition: s.transition || 'cut',
  }
}
const fromEp = (ep: Episode): DScene[] =>
  ep.scenes.map((sc) => ({ key: `c${sc.id}`, id: sc.id, title: sc.title, summary: sc.summary, location: sc.location, characters: sc.characters, approved: sc.approved, shots: sc.shots.map(fromShot) }))

const shotFields = (s: DShot) => [s.description, s.image_prompt, s.technique, s.move, s.intensity, s.duration_sec, s.narration, s.speaker, s.sfx, s.transition]
const structure = (d: DScene[]) => JSON.stringify(d.map((sc) => [sc.id ?? 'new', sc.title, sc.summary, sc.location, sc.shots.map((s) => s.id ?? 'new')]))
const toPayload = (s: DShot) => ({
  description: s.description.trim(),
  image_prompt: s.image_prompt.trim(),
  technique: s.technique,
  camera: { move: s.move, intensity: s.intensity },
  duration_sec: s.duration_sec,
  narration: s.narration,
  speaker: s.speaker,
  sfx: s.sfx,
  transition: s.transition,
})

export function StoryboardEditor({ ep, page, speakers, editable, structureEditable, hasMedia, onSavedEp, onChanged, onRegenerate }: {
  ep: Episode
  page: PageDetail | undefined
  speakers: string[]
  editable: boolean
  structureEditable: boolean
  hasMedia: boolean
  onSavedEp: (e: Episode) => void
  onChanged: () => void
  onRegenerate: () => void
}) {
  const { t, f } = useI18n()
  const confirm = useConfirm()
  const fm = useFormats()
  const server = useMemo(() => fromEp(ep), [ep.updated_at, ep.scenes.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const [d, setD] = useState<DScene[]>(server)
  const dirtyRef = useRef(false)
  const forceReset = useRef(false)
  useEffect(() => {
    if (forceReset.current || !dirtyRef.current) {
      setD(server)
      forceReset.current = false
    }
  }, [server])
  const serverSig = useMemo(() => JSON.stringify(server), [server])
  const dirty = JSON.stringify(d) !== serverSig
  dirtyRef.current = dirty
  const act = useAction()
  const allowed = page?.profiles.production.allowed_techniques as string[] | undefined
  const allTech = fm.data?.techniques ?? ['still_kenburns']
  const techOptions = (cur: string) => {
    const base = allowed && allowed.length ? allowed : allTech
    return Array.from(new Set([...base, cur])).map((k) => ({ value: k, label: t(('tech.' + k) as 'tech.still_kenburns') }))
  }
  const serverShots = useMemo(() => new Map(ep.scenes.flatMap((sc) => sc.shots).map((s) => [s.id, s])), [ep])
  const total = d.reduce((n, sc) => n + sc.shots.reduce((m, s) => m + (s.duration_sec || 0), 0), 0)
  const invalid = d.some((sc) => sc.shots.length === 0 || sc.shots.some((s) => !s.description.trim() || !s.image_prompt.trim() || !(s.duration_sec >= 1 && s.duration_sec <= 20)))
  const structural = structure(d) !== structure(server)

  const upShot = (si: number, hi: number, patch: Partial<DShot>) => setD(d.map((sc, i) => (i === si ? { ...sc, shots: sc.shots.map((s, j) => (j === hi ? { ...s, ...patch } : s)) } : sc)))
  const upScene = (si: number, patch: Partial<DScene>) => setD(d.map((sc, i) => (i === si ? { ...sc, ...patch } : sc)))
  const newShot = (): DShot => ({ key: nk(), description: '', image_prompt: '', technique: (allowed && allowed[0]) || 'still_kenburns', move: 'zoom_in', intensity: 0.5, duration_sec: 4, narration: '', speaker: '', sfx: '', transition: 'cut' })
  const moveIn = <T,>(arr: T[], i: number, dir: -1 | 1): T[] => {
    const j = i + dir
    if (j < 0 || j >= arr.length) return arr
    const c = [...arr]
    ;[c[i], c[j]] = [c[j], c[i]]
    return c
  }

  const save = async () => {
    if (structural) {
      if (hasMedia && !(await confirm({ message: t('sbd.structure_confirm'), confirmLabel: t('common.save'), danger: true }))) return
      const body = { scenes: d.map((sc) => ({ title: sc.title.trim() || t('sbd.scene_n', { n: 1 }), summary: sc.summary, location: sc.location, characters: sc.characters, shots: sc.shots.map(toPayload) })) }
      const e = await act.run(() => api.put<Episode>(`/episodes/${ep.id}/storyboard`, body), { success: t('common.saved') })
      if (e) {
        forceReset.current = true
        onSavedEp(e)
      }
      return
    }
    const changed = d.flatMap((sc) => sc.shots.filter((s) => s.id && JSON.stringify(shotFields(s)) !== JSON.stringify(shotFields(fromShot(serverShots.get(s.id!)!)))))
    const ok = await act.run(async () => {
      await Promise.all(changed.map((s) => api.patch(`/shots/${s.id}`, toPayload(s))))
      return true
    }, { success: t('sbd.saved_shots', { n: changed.length }) })
    if (ok) {
      forceReset.current = true
      onChanged()
    }
  }

  const est = ep.estimate as EpisodeEstimate | undefined
  return (
    <div className="stack">
      {!editable && <Notice tone="info">{t('sbd.readonly')}</Notice>}
      {editable && hasMedia && <Notice tone="info">{t('sbd.partial_note')}</Notice>}
      <Card>
        <div className="row" style={{ gap: '1.5rem' }}>
          <span><b>{f.num(d.length)}</b> <span className="muted">{t('sbd.scenes')}</span></span>
          <span><b>{f.num(d.reduce((n, sc) => n + sc.shots.length, 0))}</b> <span className="muted">{t('sbd.shots')}</span></span>
          <span><b>{f.duration(total)}</b> <span className="muted">{t('sbd.total_len')}</span></span>
          <span className="muted">{t('sbd.target')}: {f.duration(ep.duration_sec)}</span>
        </div>
        {est?.modes && (
          <p className="small muted" style={{ marginBlockStart: '0.5rem' }}>
            {t('sbd.estimate_line', { p: f.num(est.modes.preview?.gpu_minutes ?? 0, 1), f: f.num(est.modes.final?.gpu_minutes ?? 0, 1) })}
            {dirty ? ` ${t('sbd.estimate_stale')}` : ''}
          </p>
        )}
      </Card>

      {d.map((sc, si) => (
        <Card
          key={sc.key}
          title={<span>{t('sbd.scene_n', { n: si + 1 })}{sc.title ? ` — ${sc.title}` : ''}</span>}
          actions={
            editable && structureEditable ? (
              <>
                <Button size="sm" variant="ghost" iconOnly icon="up" aria-label={t('script.move_up')} disabled={si === 0} onClick={() => setD(moveIn(d, si, -1))} />
                <Button size="sm" variant="ghost" iconOnly icon="down" aria-label={t('script.move_down')} disabled={si === d.length - 1} onClick={() => setD(moveIn(d, si, 1))} />
                <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} disabled={d.length <= 1} onClick={() => setD(d.filter((_, i) => i !== si))} />
              </>
            ) : undefined
          }
        >
          <div className="stack">
            <div className="grid-2">
              <TextField label={t('sbd.scene_title')} value={sc.title} onChange={(v) => upScene(si, { title: v })} disabled={!editable || !structureEditable} />
              <TextField label={t('sbd.location')} value={sc.location} onChange={(v) => upScene(si, { location: v })} disabled={!editable || !structureEditable} />
            </div>
            <AreaField label={t('sbd.scene_summary')} compact value={sc.summary} onChange={(v) => upScene(si, { summary: v })} disabled={!editable || !structureEditable} />
            {sc.characters.length > 0 && <div className="row small muted">{t('sbd.characters')}: {sc.characters.join('، ')}</div>}
            {sc.id && !dirty && hasMedia && (
              <CheckField label={t('sbd.scene_approved')} checked={sc.approved} onChange={async (v) => { await api.post(`/scenes/${sc.id}/approve`, { approved: v }).catch(() => undefined); onChanged() }} />
            )}
            <div className="stack">
              {sc.shots.map((sh, hi) => (
                <ShotCard
                  key={sh.key}
                  n={hi + 1}
                  sh={sh}
                  server={sh.id ? serverShots.get(sh.id) : undefined}
                  editable={editable}
                  structureEditable={structureEditable}
                  dirty={dirty}
                  techOptions={techOptions(sh.technique)}
                  speakers={speakers}
                  onChange={(p) => upShot(si, hi, p)}
                  onMove={(dir) => upScene(si, { shots: moveIn(sc.shots, hi, dir) })}
                  onRemove={() => upScene(si, { shots: sc.shots.filter((_, j) => j !== hi) })}
                  canRemove={sc.shots.length > 1}
                  onChanged={onChanged}
                  onRegenerate={onRegenerate}
                  hasMedia={hasMedia}
                  epState={ep.state}
                />
              ))}
              {editable && structureEditable && (
                <div>
                  <Button size="sm" icon="plus" onClick={() => upScene(si, { shots: [...sc.shots, newShot()] })}>{t('sbd.add_shot')}</Button>
                </div>
              )}
            </div>
          </div>
        </Card>
      ))}
      {editable && structureEditable && (
        <div>
          <Button icon="plus" onClick={() => setD([...d, { key: nk(), title: '', summary: '', location: '', characters: [], approved: false, shots: [newShot()] }])}>{t('sbd.add_scene')}</Button>
        </div>
      )}

      {editable && (
        <div className="sticky-actions">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty || invalid} onClick={save}>{t('sbd.save')}</Button>
          <Button disabled={!dirty} onClick={() => setD(server)}>{t('prof.revert')}</Button>
          {dirty && !structural && <span className="small muted">{t('sbd.only_changed')}</span>}
          {dirty && structural && hasMedia && <span className="small" style={{ color: 'var(--warn)' }}>{t('sbd.structure_warn')}</span>}
          {invalid && <span className="small" style={{ color: 'var(--err)' }}>{t('sbd.invalid')}</span>}
        </div>
      )}
    </div>
  )
}

function ShotCard({ n, sh, server, editable, structureEditable, dirty, techOptions, speakers, onChange, onMove, onRemove, canRemove, onChanged, onRegenerate, hasMedia, epState }: {
  n: number
  sh: DShot
  server: Shot | undefined
  editable: boolean
  structureEditable: boolean
  dirty: boolean
  techOptions: { value: string; label: string }[]
  speakers: string[]
  onChange: (p: Partial<DShot>) => void
  onMove: (dir: -1 | 1) => void
  onRemove: () => void
  canRemove: boolean
  onChanged: () => void
  onRegenerate: () => void
  hasMedia: boolean
  epState: string
}) {
  const { t, f, tr } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const notes = server?.estimate?.notes ?? []
  const fallback = !IMPLEMENTED_TECHNIQUES.includes(sh.technique) || notes.includes('falls_back_to_still_kenburns')
  const canAct = !!server && hasMedia && ['asset_generation', 'animation', 'assembly', 'quality_review', 'ready_for_approval', 'failed'].includes(epState)
  const regenerate = async () => {
    if (!server) return
    if (!(await confirm({ message: t('sbd.regen_confirm'), confirmLabel: t('sbd.regen') }))) return
    const r = await act.run(async () => {
      await api.post(`/shots/${server.id}/regenerate`, { what: 'all', mode: 'preview' })
      return true
    }, { success: t('sbd.regen_started') })
    if (r) {
      onChanged()
      onRegenerate()
    }
  }
  const approve = () => server && act.run(async () => { await api.post(`/shots/${server.id}/approve`, { approved: !server.approved }); onChanged() })
  return (
    <div className={'shot-card' + (server?.approved ? ' approved' : '')}>
      <div className="shot-media">
        {server?.keyframe ? (
          <img className="thumb" src={server.keyframe.url} alt={t('sbd.keyframe_alt', { n })} loading="lazy" />
        ) : (
          <div className="thumb">{t('sbd.no_keyframe')}</div>
        )}
        {server?.narration_asset && <audio controls preload="none" src={server.narration_asset.url} aria-label={t('sbd.audio_alt', { n })} />}
      </div>
      <div className="stack">
        <div className="row between">
          <span className="strong">{t('sbd.shot_n', { n })}</span>
          <span className="row">
            {server?.approved && <Badge tone="ok">{t('sbd.approved')}</Badge>}
            {server && <Badge title={t('sbd.estimate_hint')}>{t('sbd.gpu_est', { t: f.duration(server.estimate.gpu_seconds) })}</Badge>}
            {editable && structureEditable && (
              <>
                <Button size="sm" variant="ghost" iconOnly icon="up" aria-label={t('script.move_up')} onClick={() => onMove(-1)} />
                <Button size="sm" variant="ghost" iconOnly icon="down" aria-label={t('script.move_down')} onClick={() => onMove(1)} />
                <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} disabled={!canRemove} onClick={onRemove} />
              </>
            )}
          </span>
        </div>
        <AreaField label={t('sbd.description')} compact value={sh.description} onChange={(v) => onChange({ description: v })} disabled={!editable} />
        <AreaField label={t('sbd.image_prompt')} compact value={sh.image_prompt} onChange={(v) => onChange({ image_prompt: v })} disabled={!editable} hint={t('sbd.prompt_hint')} dir="ltr" />
        <div className="grid-3">
          <SelectField label={t('sbd.technique')} value={sh.technique} onChange={(v) => onChange({ technique: v })} options={techOptions} disabled={!editable} />
          <SelectField label={t('sbd.camera')} value={sh.move} onChange={(v) => onChange({ move: v })} options={CAMERA_MOVES.map((m) => ({ value: m, label: tr('cam.' + m, m) }))} disabled={!editable} />
          <NumberField label={t('sbd.intensity')} min={0} max={1} step={0.1} value={sh.intensity} onChange={(v) => onChange({ intensity: v ?? 0.5 })} disabled={!editable} />
        </div>
        {fallback && <Notice tone="warn">{t('sbd.fallback')}</Notice>}
        {notes.includes('clips_chained') && <Notice tone="info">{t('sbd.chained')}</Notice>}
        <div className="grid-3">
          <NumberField label={t('sbd.duration')} min={1} max={20} step={0.5} value={sh.duration_sec} onChange={(v) => onChange({ duration_sec: v ?? 4 })} disabled={!editable} />
          <TextField label={t('script.speaker')} list="speakers" value={sh.speaker} onChange={(v) => onChange({ speaker: v })} disabled={!editable} />
          <SelectField label={t('sbd.transition')} value={sh.transition === 'crossfade' ? 'crossfade' : 'cut'} onChange={(v) => onChange({ transition: v })} options={[{ value: 'cut', label: t('sbd.tr_cut') }, { value: 'crossfade', label: t('sbd.tr_crossfade') }]} disabled={!editable} />
        </div>
        <AreaField label={t('sbd.narration')} compact value={sh.narration} onChange={(v) => onChange({ narration: v })} disabled={!editable} />
        {server?.last_error && <Notice tone="err">{server.last_error}</Notice>}
        {canAct && (
          <div className="row">
            <Button size="sm" icon="check" disabled={dirty} busy={act.busy} onClick={approve}>{server?.approved ? t('sbd.unapprove') : t('sbd.approve')}</Button>
            <Button size="sm" icon="refresh" disabled={dirty} busy={act.busy} onClick={regenerate}>{t('sbd.regen')}</Button>
            {dirty && <span className="small muted">{t('pub.save_first')}</span>}
          </div>
        )}
      </div>
    </div>
  )
}
