import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { CastingRow, DesignSheet, Episode, PageDetail, Retake, StageRow, StudioPayload } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { LocalJob } from '../series/dev/common'
import { AreaField, Badge, Button, Card, Empty, ErrorState, Loading, Notice, SelectField, TextField, type Tone } from '../../components/ui'
import { useAction, useJobRunner, useQuery } from '../../hooks'
import { useI18n } from '../../i18n'

const STAGE_TONE: Record<StageRow['status'], Tone> = { todo: 'neutral', ready: 'warn', stale: 'err', approved: 'ok', auto: 'info' }
const isActive = (s: string) => s === 'queued' || s === 'running'

/** Pre-production of one episode, the studio way: animatic, design sheets, voice casting, retakes, translation and the approval gate. */
export function Studio({ ep, page, onChanged }: { ep: Episode; page: PageDetail | undefined; onChanged: () => void }) {
  const { t } = useI18n()
  const jobsKey = ep.jobs.filter((j) => j.kind.startsWith('studio.')).map((j) => j.id + j.status).join(',')
  const q = useQuery<StudioPayload>(`/episodes/${ep.id}/studio`, { interval: (d) => (d && ep.jobs.some((j) => isActive(j.status) && j.kind.startsWith('studio.')) ? 3000 : false) })
  useEffect(() => { q.reload() }, [jobsKey, ep.state, ep.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Loading />
  const st = q.data
  const reload = () => { q.reload(); onChanged() }
  const hasBoard = ep.scenes.length > 0
  const set = (d: StudioPayload) => q.setData(d)
  return (
    <div className="stack">
      <p className="muted">{t('studio.intro')}</p>
      {!st.report.studio_mode && <Notice tone="info">{t('studio.mode_off')}</Notice>}
      {st.report.studio_mode && ep.state === 'storyboarding' && !st.report.gate_approved && <Notice tone="warn">{t('studio.gate_needed')}</Notice>}
      <StageBoard ep={ep} st={st} set={set} />
      {!hasBoard ? <Empty icon="film" title={t('studio.need_board')} text={t('studio.need_board_text')} /> : (
        <>
          <AnimaticCard ep={ep} st={st} reload={reload} />
          <DesignCard ep={ep} st={st} reload={reload} />
          <CastingCard ep={ep} st={st} set={set} reload={reload} />
          <RetakeCard ep={ep} st={st} reload={reload} />
        </>
      )}
      <TranslateCard ep={ep} st={st} page={page} reload={reload} />
      <PostCard ep={ep} />
    </div>
  )
}

function StageBoard({ ep, st, set }: { ep: Episode; st: StudioPayload; set: (d: StudioPayload) => void }) {
  const { t } = useI18n()
  const act = useAction()
  const gate = st.report.stages.find((s) => s.key === 'gate')!
  const call = async (key: string, what: 'approve' | 'revoke') => {
    const d = await act.run(() => api.post<StudioPayload>(`/episodes/${ep.id}/studio/stages/${key}/${what}`, {}))
    if (d) set(d)
  }
  return (
    <Card title={t('studio.stages')}>
      <ol className="stage-board">
        {st.report.stages.map((s, i) => (
          <li key={s.key} className={'stage st-' + s.status}>
            <div className="row between" style={{ flexWrap: 'nowrap' }}>
              <span className="strong"><span className="num">{i + 1}</span> {t(('studio.stage_' + s.key) as 'studio.stage_script')}</span>
              <Badge tone={STAGE_TONE[s.status]}>{t(('studio.st_' + s.status) as 'studio.st_todo')}</Badge>
            </div>
            <div className="small muted">{s.required ? t('studio.needs_you') : t('studio.auto_pass')}</div>
            {s.key !== 'script' && s.key !== 'storyboard' && s.key !== 'gate' && (
              <div className="row">
                {(s.status === 'ready' || s.status === 'auto') && <Button size="sm" variant="primary" icon="check" busy={act.busy} onClick={() => call(s.key, 'approve')}>{t('studio.approve')}</Button>}
                {s.status === 'approved' && <Button size="sm" busy={act.busy} onClick={() => call(s.key, 'revoke')}>{t('studio.revoke')}</Button>}
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="stack-sm" style={{ marginBlockStart: '1rem' }}>
        {gate.blocking && gate.blocking.length > 0 && <Notice tone="warn">{t('studio.blocking')}: {gate.blocking.map((k) => t(('studio.stage_' + k) as 'studio.stage_script')).join(' · ')}</Notice>}
        <div className="row dev-gatebar">
          {gate.status !== 'approved' ? (
            <Button variant="primary" icon="flag" busy={act.busy} disabled={gate.status !== 'ready'} onClick={() => call('gate', 'approve')}>{t('studio.gate_approve')}</Button>
          ) : (
            <>
              <Badge tone="ok">{t('studio.gate_done')}</Badge>
              <Button size="sm" busy={act.busy} onClick={() => call('gate', 'revoke')}>{t('studio.revoke')}</Button>
            </>
          )}
          <span className="small muted">{t('studio.gate_note')}</span>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- animatic
function AnimaticCard({ ep, st, reload }: { ep: Episode; st: StudioPayload; reload: () => void }) {
  const { t, f } = useI18n()
  const runner = useJobRunner({ onSucceeded: reload })
  const a = st.animatic
  return (
    <Card title={t('animatic.title')} actions={<Badge tone={a.status === 'fresh' ? 'ok' : a.status === 'stale' ? 'err' : 'neutral'}>{t(('animatic.st_' + a.status) as 'animatic.st_fresh')}</Badge>}>
      <div className="stack">
        <p className="small muted">{t('animatic.intro')}</p>
        <div className="row">
          <Button variant="primary" icon="film" busy={runner.starting || runner.busy} onClick={() => runner.start(() => api.post(`/episodes/${ep.id}/studio/animatic`, {}))}>
            {a.asset ? t('animatic.rebuild') : t('animatic.build')}
          </Button>
          <span className="small muted">{t('animatic.cost_note')}</span>
        </div>
        {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        {a.status === 'stale' && <Notice tone="warn">{t('animatic.stale')}</Notice>}
        {a.asset && (
          <div className="stack-sm">
            <video className="animatic-video" src={a.asset.url} controls preload="metadata" playsInline aria-label={t('animatic.title')} />
            <div className="row small muted">
              <span>{a.asset.duration_sec ? f.duration(a.asset.duration_sec) : '—'}</span>
              <span>{t('animatic.stills', { k: a.asset.stills?.keyframes ?? 0, p: a.asset.stills?.placeholders ?? 0 })}</span>
              <span>{t(('animatic.audio_' + (a.asset.scratch_audio || 'none')) as 'animatic.audio_none')}</span>
            </div>
            {(a.built_with ?? []).map((n, i) => <div key={i} className="small muted">{n}</div>)}
          </div>
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- design sheets
const SHEET_KINDS = ['character', 'expression', 'background', 'prop', 'colour_script'] as const

function DesignCard({ ep, st, reload }: { ep: Episode; st: StudioPayload; reload: () => void }) {
  const { t, lang } = useI18n()
  const runner = useJobRunner({ onSucceeded: reload })
  const [adding, setAdding] = useState(false)
  return (
    <Card title={t('design.title')} actions={<Badge>{t('design.n', { n: st.design_sheets.length })}</Badge>}>
      <div className="stack">
        <p className="small muted">{t('design.intro')}</p>
        <div className="row">
          <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} onClick={() => runner.start(() => api.post(`/episodes/${ep.id}/studio/design/generate`, { language: lang }))}>
            {st.design_sheets.length ? t('design.regenerate') : t('design.generate')}
          </Button>
          <Button icon="plus" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>{t('design.add')}</Button>
        </div>
        {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        {adding && <NewSheet ep={ep} onDone={() => { setAdding(false); reload() }} />}
        {st.design_sheets.length === 0 ? <Empty icon="palette" title={t('design.empty')} text={t('design.empty_text')} /> : (
          <div className="grid-auto">
            {st.design_sheets.map((s) => <SheetCard key={s.id + ':' + s.status + ':' + s.approved + ':' + (s.image_url ?? '')} sheet={s} reload={reload} />)}
          </div>
        )}
      </div>
    </Card>
  )
}

function NewSheet({ ep, onDone }: { ep: Episode; onDone: () => void }) {
  const { t } = useI18n()
  const act = useAction()
  const [d, setD] = useState({ kind: 'prop', subject: '', prompt: '', notes: '' })
  return (
    <div className="card soft flat stack-sm">
      <div className="grid-2">
        <SelectField label={t('design.kind')} value={d.kind} onChange={(v) => setD({ ...d, kind: v })} options={SHEET_KINDS.map((k) => ({ value: k, label: t(('design.k_' + k) as 'design.k_prop') }))} />
        <TextField label={t('design.subject')} required value={d.subject} onChange={(v) => setD({ ...d, subject: v })} />
      </div>
      <AreaField label={t('design.prompt')} className="ltr" compact value={d.prompt} onChange={(v) => setD({ ...d, prompt: v })} hint={t('design.prompt_hint')} />
      <AreaField label={t('design.notes')} compact value={d.notes} onChange={(v) => setD({ ...d, notes: v })} />
      <div className="row">
        <Button variant="primary" icon="check" busy={act.busy} disabled={!d.subject.trim()} onClick={async () => { if (await act.run(async () => { await api.post(`/episodes/${ep.id}/studio/design-sheets`, d); return true }, { success: t('common.saved') })) onDone() }}>{t('common.add')}</Button>
        <Button onClick={onDone}>{t('common.cancel')}</Button>
      </div>
    </div>
  )
}

function SheetCard({ sheet, reload }: { sheet: DesignSheet; reload: () => void }) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const runner = useJobRunner({ onSucceeded: reload })
  const [d, setD] = useState({ subject: sheet.subject, prompt: sheet.prompt, notes: sheet.notes })
  const dirty = d.subject !== sheet.subject || d.prompt !== sheet.prompt || d.notes !== sheet.notes
  const save = () => act.run(async () => { await api.patch(`/design-sheets/${sheet.id}`, d); reload() }, { success: t('common.saved') })
  return (
    <article className="card stack-sm sheet" aria-label={sheet.subject}>
      <div className="row between" style={{ flexWrap: 'nowrap' }}>
        <Badge>{t(('design.k_' + sheet.kind) as 'design.k_prop')}</Badge>
        <span className="row" style={{ gap: '0.25rem' }}>
          <Badge tone={sheet.author === 'ai' ? 'primary' : 'neutral'}>{sheet.author === 'ai' ? t('idea.by_ai') : t('idea.by_human')}</Badge>
          {sheet.approved && <Badge tone="ok">{t('studio.st_approved')}</Badge>}
        </span>
      </div>
      {sheet.image_url && <img className="sheet-img" src={sheet.image_url} alt={sheet.subject} loading="lazy" />}
      {sheet.palette.length > 0 && <div className="row">{sheet.palette.map((c, i) => <span key={i} className="chip-color"><i style={{ background: c }} /> <span className="ltr small">{c}</span></span>)}</div>}
      <TextField label={t('design.subject')} value={d.subject} onChange={(v) => setD({ ...d, subject: v })} />
      <AreaField label={t('design.prompt')} className="ltr" compact value={d.prompt} onChange={(v) => setD({ ...d, prompt: v })} />
      <AreaField label={t('design.notes')} compact value={d.notes} onChange={(v) => setD({ ...d, notes: v })} />
      {sheet.last_error && <Notice tone="err">{sheet.last_error}</Notice>}
      {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
      <div className="row">
        <Button size="sm" variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
        <Button size="sm" icon="image" busy={runner.starting || runner.busy} disabled={dirty} onClick={() => runner.start(() => api.post(`/design-sheets/${sheet.id}/image`, {}))}>{sheet.image_url ? t('design.remake_image') : t('design.make_image')}</Button>
        <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.delete')} onClick={async () => { if (await confirm({ message: t('design.delete_confirm'), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/design-sheets/${sheet.id}`); reload() }) }} />
      </div>
    </article>
  )
}

// ---------------------------------------------------------------- casting
function CastingCard({ ep, st, set, reload }: { ep: Episode; st: StudioPayload; set: (d: StudioPayload) => void; reload: () => void }) {
  const { t, lang } = useI18n()
  const act = useAction()
  const runner = useJobRunner({ onSucceeded: reload })
  const current = (r: CastingRow) => (r.engine && r.voice_id ? `${r.engine}:${r.voice_id}` : '')
  const [pick, setPick] = useState<Record<number, string>>({})
  useEffect(() => setPick({}), [JSON.stringify(st.casting)])
  const rows = st.casting
  const dirty = rows.some((r) => pick[r.character] !== undefined && pick[r.character] !== current(r))
  const save = async () => {
    const casting = rows.filter((r) => pick[r.character] !== undefined).map((r) => ({ character: r.character, voice_id: pick[r.character] }))
    const d = await act.run(() => api.put<StudioPayload>(`/episodes/${ep.id}/studio/casting`, { casting }), { success: t('common.saved') })
    if (d) set(d)
  }
  const opts = useMemo(() => [{ value: '', label: t('cast.none') }, ...st.voices.map((v) => ({ value: v.id, label: v.label + (v.installed ? '' : ' · ' + t('cast.not_installed')) + (v.commercial_ok === false ? ' · ' + t('cast.noncommercial') : ''), disabled: !v.installed }))], [st.voices, t])
  return (
    <Card title={t('cast.title')}>
      <div className="stack">
        <p className="small muted">{t('cast.intro')}</p>
        <div className="row">
          <Button variant="primary" icon="mic" busy={runner.starting || runner.busy} disabled={rows.length === 0} onClick={() => runner.start(() => api.post(`/episodes/${ep.id}/studio/casting/suggest`, { language: lang }))}>{t('cast.suggest')}</Button>
          <Button icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
        </div>
        {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        {rows.length === 0 ? <Empty icon="users" title={t('cast.empty')} text={t('cast.empty_text')} /> : (
          <div className="stack">
            {rows.map((r) => (
              <div key={r.character} className="row cast-row" style={{ alignItems: 'flex-end' }}>
                <div className="grow"><div className="strong">{r.name}</div><div className="small muted">{[r.role, r.personality].filter(Boolean).join(' · ')}</div></div>
                <SelectField className="cast-select" label={t('cast.voice')} value={pick[r.character] ?? current(r)} onChange={(v) => setPick({ ...pick, [r.character]: v })} options={opts} />
                <Badge tone={r.has_voice ? 'ok' : 'warn'}>{r.has_voice ? t('cast.set') : t('cast.missing')}</Badge>
              </div>
            ))}
          </div>
        )}
        {st.voices.every((v) => !v.installed) && <Notice tone="warn">{t('cast.no_voices')}</Notice>}
        <p className="small muted">{t('cast.narrator_note')}</p>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- retakes
function RetakeCard({ ep, st, reload }: { ep: Episode; st: StudioPayload; reload: () => void }) {
  const { t } = useI18n()
  const act = useAction()
  const shots = ep.scenes.flatMap((sc) => sc.shots.map((sh) => ({ id: sh.id, label: `${sc.index}.${sh.index} · ${(sh.description || sh.narration).slice(0, 48)}` })))
  const [shot, setShot] = useState(String(shots[0]?.id ?? ''))
  const [scope, setScope] = useState('keyframe')
  const [reason, setReason] = useState('')
  const go = async () => {
    const r = await act.run(() => api.post(`/shots/${shot}/retake`, { scope, reason }), { success: t('retake.sent') })
    if (r) { setReason(''); reload() }
  }
  const tone = (r: Retake): Tone => (r.status === 'done' ? 'ok' : r.status === 'cancelled' ? 'neutral' : 'warn')
  return (
    <Card title={t('retake.title')}>
      <div className="stack">
        <p className="small muted">{t('retake.intro')}</p>
        <div className="grid-2">
          <SelectField label={t('retake.shot')} value={shot} onChange={setShot} options={shots.map((s) => ({ value: String(s.id), label: s.label }))} />
          <SelectField label={t('retake.scope')} value={scope} onChange={setScope} options={['keyframe', 'narration', 'clip', 'all'].map((k) => ({ value: k, label: t(('retake.scope_' + k) as 'retake.scope_all') }))} />
        </div>
        <AreaField label={t('retake.reason')} compact value={reason} onChange={setReason} hint={t('retake.reason_hint')} />
        <div><Button variant="primary" icon="refresh" busy={act.busy} disabled={!reason.trim() || !shot} onClick={go}>{t('retake.send')}</Button></div>
        {st.retakes.length > 0 && (
          <ul className="plain-list stack-sm">
            {st.retakes.map((r) => (
              <li key={r.id} className="row between">
                <span><Badge tone={tone(r)}>{t(('retake.st_' + r.status) as 'retake.st_open')}</Badge> <strong>{r.shot_label}</strong> · {t(('retake.scope_' + r.scope) as 'retake.scope_all')} — {r.reason}</span>
                {r.status === 'open' && <Button size="sm" variant="ghost" onClick={() => act.run(async () => { await api.post(`/retakes/${r.id}/cancel`, {}); reload() })}>{t('common.cancel')}</Button>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- translation
function TranslateCard({ ep, st, page, reload }: { ep: Episode; st: StudioPayload; page: PageDetail | undefined; reload: () => void }) {
  const { t } = useI18n()
  const runner = useJobRunner({ onSucceeded: reload })
  const [target, setTarget] = useState<string>('')
  const src = (ep.script as { language?: string }).language || ep.language || page?.languages?.[0] || 'fa'
  const targets = (['fa', 'en'] as const).filter((l) => l !== src.slice(0, 2))
  const tl = target || targets[0]
  const has = Object.keys(st.translations)
  const trs = ep.translations ?? {}
  if (!ep.script || !('blocks' in ep.script) || ep.script.blocks.length === 0) return null
  return (
    <Card title={t('trans.title')}>
      <div className="stack">
        <p className="small muted">{t('trans.intro')}</p>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <SelectField label={t('trans.to')} value={tl} onChange={setTarget} options={targets.map((l) => ({ value: l, label: l === 'fa' ? 'فارسی' : 'English' }))} />
          <Button variant="primary" icon="globe" busy={runner.starting || runner.busy} onClick={() => runner.start(() => api.post(`/episodes/${ep.id}/translate`, { language: tl }))}>{t('trans.go')}</Button>
        </div>
        {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        {has.map((l) => (
          <div key={l} className="card soft flat stack-sm">
            <div className="row"><Badge tone="ok">{l === 'fa' ? 'فارسی' : 'English'}</Badge><span className="small muted">{t('trans.info', { m: st.translations[l].model || st.translations[l].provider || '—', n: st.translations[l].shots })}</span></div>
            <ol className="small steps-list" dir={l === 'fa' ? 'rtl' : 'ltr'}>{(trs[l]?.script?.blocks ?? []).slice(0, 3).map((b, i) => <li key={i}>{b.text}</li>)}</ol>
          </div>
        ))}
        <p className="small muted">{t('trans.note')}</p>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- post-production (what production's pipeline does after the gate)
function PostCard({ ep }: { ep: Episode }) {
  const { t } = useI18n()
  const steps: { key: string; on: boolean }[] = [
    { key: 'assets', on: ['asset_generation', 'animation'].includes(ep.state) },
    { key: 'assembly', on: ep.state === 'assembly' },
    { key: 'qc', on: ep.state === 'quality_review' },
    { key: 'approval', on: ['ready_for_approval', 'approved', 'scheduled', 'published'].includes(ep.state) },
  ]
  return (
    <Card title={t('post.title')}>
      <p className="small muted">{t('post.intro')}</p>
      <ul className="plain-list stack-sm">
        {steps.map((s) => (
          <li key={s.key} className="row between"><span>{t(('post.' + s.key) as 'post.assets')}</span>{s.on && <Badge tone="info">{t('post.now')}</Badge>}</li>
        ))}
      </ul>
      <p className="small muted">{t('post.note')}</p>
    </Card>
  )
}
