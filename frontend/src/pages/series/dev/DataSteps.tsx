import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../api/client'
import type { Development } from '../../../api/types'
import { TagsField, AreaField, Badge, Button, Card, Empty, NumberField, SelectField, TextField, Notice } from '../../../components/ui'
import { useToast } from '../../../components/feedback'
import { useAction, useJobRunner } from '../../../hooks'
import { useI18n } from '../../../i18n'
import { LocalJob, SourceBadges, StepFrame, type StepProps } from './common'

// ================================================================== consequence map (butterfly effect)
interface MapNode {
  id: string
  title: string
  description: string
  parent: string
  kind: string
  episode_hint: number
}
const NODE_KINDS = ['divergence', 'direct', 'ripple', 'character', 'world', 'theme']

export function MapStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, step, setDev } = p
  const stored: MapNode[] = step.data?.nodes ?? []
  const [nodes, setNodes] = useState<MapNode[]>(stored)
  useEffect(() => setNodes(stored), [JSON.stringify(stored)]) // eslint-disable-line react-hooks/exhaustive-deps
  const [instruction, setInstruction] = useState('')
  const act = useAction()
  const runner = useJobRunner({ onSucceeded: () => api.get<Development>(`/series/${dev.series.id}/development`).then(setDev) })
  const dirty = JSON.stringify(nodes) !== JSON.stringify(stored)
  const approved = (dev.ideas[Object.keys(dev.ideas)[0]] ?? []).some((i) => i.status === 'approved') || Object.values(dev.ideas).some((l) => l.some((i) => i.status === 'approved'))
  const kids = useMemo(() => {
    const m = new Map<string, MapNode[]>()
    nodes.forEach((n) => m.set(n.parent, [...(m.get(n.parent) ?? []), n]))
    return m
  }, [nodes])
  const upd = (id: string, patch: Partial<MapNode>) => setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, ...patch } : n)))
  const addChild = (parent: string) => setNodes((ns) => [...ns, { id: `n${Date.now().toString(36)}`, title: '', description: '', parent, kind: parent ? 'ripple' : 'divergence', episode_hint: 0 }])
  const remove = (id: string) => setNodes((ns) => { const me = ns.find((n) => n.id === id); return ns.filter((n) => n.id !== id).map((n) => (n.parent === id ? { ...n, parent: me?.parent ?? '' } : n)) })
  const save = () => act.run(async () => { setDev(await api.put<Development>(`/series/${dev.series.id}/dev/steps/${step.key}/data`, { data: { nodes } })) }, { success: t('common.saved') })
  const render = (parent: string, depth: number): React.ReactNode =>
    (kids.get(parent) ?? []).map((n) => (
      <li key={n.id} style={{ listStyle: 'none' }}>
        <div className={'map-node kind-' + n.kind} style={{ marginInlineStart: depth * 20 }}>
          <div className="row">
            <SelectField label={t('map.kind')} value={n.kind} onChange={(v) => upd(n.id, { kind: v })} options={NODE_KINDS.map((k) => ({ value: k, label: t(('map.k_' + k) as 'map.k_direct') }))} />
            <TextField className="grow" label={t('map.node_title')} value={n.title} onChange={(v) => upd(n.id, { title: v })} />
            <NumberField label={t('map.episode')} min={0} max={60} value={n.episode_hint} onChange={(v) => upd(n.id, { episode_hint: v ?? 0 })} className="narrow" />
          </div>
          <AreaField label={t('map.desc')} compact value={n.description} onChange={(v) => upd(n.id, { description: v })} />
          <div className="row">
            <Button size="sm" icon="plus" onClick={() => addChild(n.id)}>{t('map.add_child')}</Button>
            <Button size="sm" variant="ghost" icon="trash" onClick={() => remove(n.id)}>{t('common.remove')}</Button>
          </div>
        </div>
        <ul style={{ padding: 0, margin: '0.5rem 0 0' }} className="stack-sm">{render(n.id, depth + 1)}</ul>
      </li>
    ))
  return (
    <StepFrame {...p}>
      {!approved && <Notice tone="warn">{t('map.need_idea')}</Notice>}
      <Card title={t('map.title')}>
        <div className="stack">
          <p className="small muted">{t('map.intro')}</p>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <TextField className="grow" label={t('idea.instruction')} value={instruction} onChange={setInstruction} placeholder={t('map.instruction_ph')} />
            <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} disabled={!approved} onClick={() => runner.start(() => api.post(`/series/${dev.series.id}/dev/steps/${step.key}/generate`, { instruction, language: lang }))}>
              {stored.length ? t('map.regenerate') : t('map.generate')}
            </Button>
          </div>
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        </div>
      </Card>
      {nodes.length === 0 ? <Empty icon="layers" title={t('map.empty')} action={<Button icon="plus" onClick={() => addChild('')}>{t('map.add_root')}</Button>} /> : (
        <Card title={t('map.tree')} actions={<Button size="sm" icon="plus" onClick={() => addChild('')}>{t('map.add_root')}</Button>}>
          <ul style={{ padding: 0, margin: 0 }} className="stack-sm">{render('', 0)}</ul>
          <div className="row" style={{ marginBlockStart: '0.75rem' }}>
            <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
            {dirty && <Button onClick={() => setNodes(stored)}>{t('prof.revert')}</Button>}
          </div>
        </Card>
      )}
    </StepFrame>
  )
}

// ================================================================== alternative timeline
interface Row {
  when: string
  canon: string
  alternate: string
  note: string
}

export function TimelineStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, step, setDev } = p
  const stored: Row[] = step.data?.rows ?? []
  const [rows, setRows] = useState<Row[]>(stored)
  useEffect(() => setRows(stored), [JSON.stringify(stored)]) // eslint-disable-line react-hooks/exhaustive-deps
  const [instruction, setInstruction] = useState('')
  const act = useAction()
  const runner = useJobRunner({ onSucceeded: () => api.get<Development>(`/series/${dev.series.id}/development`).then(setDev) })
  const dirty = JSON.stringify(rows) !== JSON.stringify(stored)
  const upd = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const save = () => act.run(async () => { setDev(await api.put<Development>(`/series/${dev.series.id}/dev/steps/${step.key}/data`, { data: { rows, summary: step.data?.summary ?? '' } })) }, { success: t('common.saved') })
  return (
    <StepFrame {...p}>
      <Card title={t('tl.title')}>
        <div className="stack">
          <p className="small muted">{t('tl.intro')}</p>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <TextField className="grow" label={t('idea.instruction')} value={instruction} onChange={setInstruction} />
            <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} onClick={() => runner.start(() => api.post(`/series/${dev.series.id}/dev/steps/${step.key}/generate`, { instruction, language: lang }))}>
              {stored.length ? t('tl.regenerate') : t('tl.generate')}
            </Button>
          </div>
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        </div>
      </Card>
      <Card title={t('tl.rows')} actions={<Button size="sm" icon="plus" onClick={() => setRows([...rows, { when: '', canon: '', alternate: '', note: '' }])}>{t('tl.add_row')}</Button>}>
        {rows.length === 0 ? <Empty icon="clock" title={t('tl.empty')} /> : (
          <div className="stack">
            {rows.map((r, i) => (
              <div key={i} className="card soft flat stack-sm">
                <div className="row between"><strong>{i + 1}</strong><Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => setRows(rows.filter((_, j) => j !== i))} /></div>
                <TextField label={t('tl.when')} value={r.when} onChange={(v) => upd(i, { when: v })} />
                <div className="grid-2">
                  <AreaField label={t('tl.canon')} compact value={r.canon} onChange={(v) => upd(i, { canon: v })} />
                  <AreaField label={t('tl.alternate')} compact value={r.alternate} onChange={(v) => upd(i, { alternate: v })} />
                </div>
                <TextField label={t('tl.note')} value={r.note} onChange={(v) => upd(i, { note: v })} />
              </div>
            ))}
            <div className="row">
              <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
              {dirty && <Button onClick={() => setRows(stored)}>{t('prof.revert')}</Button>}
            </div>
          </div>
        )}
      </Card>
    </StepFrame>
  )
}

// ================================================================== character brief -> character bible
interface Ch {
  name: string
  role: string
  appearance: string
  personality: string
  motivations: string
  abilities: string
  catchphrases: string[]
  visual_hooks: string[]
  voice_notes: string
  is_original: boolean
}
const blankCh = (): Ch => ({ name: '', role: '', appearance: '', personality: '', motivations: '', abilities: '', catchphrases: [], visual_hooks: [], voice_notes: '', is_original: true })

export function ProfileStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, step, setDev } = p
  const toast = useToast()
  const stored: Ch[] = step.data?.characters ?? []
  const [brief, setBrief] = useState<string>(step.data?.brief ?? '')
  const [chars, setChars] = useState<Ch[]>(stored)
  useEffect(() => setChars(stored), [JSON.stringify(stored)]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = useAction()
  const runner = useJobRunner({ onSucceeded: () => api.get<Development>(`/series/${dev.series.id}/development`).then(setDev) })
  const dirty = JSON.stringify(chars) !== JSON.stringify(stored)
  const upd = (i: number, patch: Partial<Ch>) => setChars((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const save = () => act.run(async () => { setDev(await api.put<Development>(`/series/${dev.series.id}/dev/steps/${step.key}/data`, { data: { brief, characters: chars } })) }, { success: t('common.saved') })
  const sync = async () => {
    if (dirty) await save()
    const r = await act.run(() => api.post<{ characters_added: number }>(`/series/${dev.series.id}/dev/steps/${step.key}/sync-characters`, {}))
    if (r) toast.ok(t('prof.synced', { n: r.characters_added }))
  }
  return (
    <StepFrame {...p}>
      <Card title={t('prof.brief_title')}>
        <div className="stack">
          <p className="small muted">{t('prof.brief_intro')}</p>
          <AreaField label={t('prof.brief')} value={brief} onChange={setBrief} placeholder={t('prof.brief_ph')} />
          <div className="row">
            <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} disabled={!brief.trim()} onClick={() => runner.start(() => api.post(`/series/${dev.series.id}/dev/steps/${step.key}/generate`, { brief, language: lang }))}>
              {stored.length ? t('prof.regenerate') : t('prof.generate')}
            </Button>
          </div>
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        </div>
      </Card>
      {chars.map((c, i) => (
        <Card key={i} title={c.name || t('wiz.char_n', { n: i + 1 })} actions={<Button size="sm" variant="ghost" icon="trash" onClick={() => setChars(chars.filter((_, j) => j !== i))}>{t('common.remove')}</Button>}>
          <div className="stack">
            <div className="grid-2">
              <TextField label={t('char.name')} value={c.name} onChange={(v) => upd(i, { name: v })} />
              <TextField label={t('char.role')} value={c.role} onChange={(v) => upd(i, { role: v })} />
            </div>
            <AreaField label={t('char.appearance')} compact value={c.appearance} onChange={(v) => upd(i, { appearance: v })} />
            <div className="grid-2">
              <AreaField label={t('char.personality')} compact value={c.personality} onChange={(v) => upd(i, { personality: v })} />
              <AreaField label={t('char.motivations')} compact value={c.motivations} onChange={(v) => upd(i, { motivations: v })} />
            </div>
            <AreaField label={t('char.abilities')} compact value={c.abilities} onChange={(v) => upd(i, { abilities: v })} />
            <TagsField label={t('prof.catchphrases')} value={c.catchphrases} onChange={(v) => upd(i, { catchphrases: v })} />
            <TagsField label={t('prof.visual_hooks')} hint={t('prof.visual_hooks_hint')} value={c.visual_hooks} onChange={(v) => upd(i, { visual_hooks: v })} />
            <TextField label={t('prof.voice_notes')} value={c.voice_notes} onChange={(v) => upd(i, { voice_notes: v })} />
          </div>
        </Card>
      ))}
      <div className="row">
        <Button icon="plus" onClick={() => setChars([...chars, blankCh()])}>{t('wiz.add_char')}</Button>
        <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
        <Button icon="users" busy={act.busy} disabled={chars.length === 0} onClick={sync}>{t('prof.sync')}</Button>
      </div>
      <p className="small muted">{t('prof.sync_note')}</p>
    </StepFrame>
  )
}

// ================================================================== fact check
interface Claim {
  claim: string
  stance: string
  source_ids: number[]
  explanation: string
  unsupported?: boolean
}

export function FactcheckStep(p: StepProps) {
  const { t } = useI18n()
  const { dev, reload } = p
  const doc = dev.research.topic
  const stored: Claim[] = doc?.content.claims ?? []
  const [claims, setClaims] = useState<Claim[]>(stored)
  useEffect(() => setClaims(stored), [JSON.stringify(stored)]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = useAction()
  const dirty = JSON.stringify(claims) !== JSON.stringify(stored)
  const upd = (i: number, patch: Partial<Claim>) => setClaims((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const save = () => act.run(async () => { await api.patch(`/research-docs/${doc!.id}`, { content: { ...doc!.content, claims } }); reload() }, { success: t('common.saved') })
  const weak = claims.filter((c) => c.stance === 'established' && (c.source_ids?.length ?? 0) === 0).length
  return (
    <StepFrame {...p}>
      {!doc ? (
        <Notice tone="warn">{t('fc.need_research')}</Notice>
      ) : (
        <Card title={t('fc.title')} actions={<Button size="sm" icon="plus" onClick={() => setClaims([...claims, { claim: '', stance: 'speculative', source_ids: [], explanation: '' }])}>{t('fc.add')}</Button>}>
          <div className="stack">
            <p className="small muted">{t('fc.intro')}</p>
            {weak > 0 && <Notice tone="warn">{t('fc.weak', { n: weak })}</Notice>}
            {claims.map((c, i) => (
              <div key={i} className="card soft flat stack-sm">
                <div className="row between">
                  <SourceBadges dev={dev} ids={c.source_ids} />
                  <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => setClaims(claims.filter((_, j) => j !== i))} />
                </div>
                <AreaField label={t('fc.claim')} compact value={c.claim} onChange={(v) => upd(i, { claim: v })} />
                <div className="grid-2">
                  <SelectField label={t('fc.stance')} value={c.stance} onChange={(v) => upd(i, { stance: v })} options={['established', 'contested', 'speculative'].map((s) => ({ value: s, label: t(('stance.' + s) as 'stance.established') }))} />
                  <TextField label={t('fc.explanation')} value={c.explanation} onChange={(v) => upd(i, { explanation: v })} />
                </div>
                <div className="row">
                  {dev.sources.map((s) => (
                    <label key={s.id} className="check small">
                      <input type="checkbox" checked={(c.source_ids ?? []).includes(s.id)} onChange={(e) => upd(i, { source_ids: e.target.checked ? [...(c.source_ids ?? []), s.id] : (c.source_ids ?? []).filter((x) => x !== s.id) })} />
                      <span className="check-text">{t('dev.src_n', { n: s.id })} <Badge>{s.verified ? t('fc.verified') : t('fc.by_owner')}</Badge></span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <div className="row">
              <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
              {dirty && <Button onClick={() => setClaims(stored)}>{t('prof.revert')}</Button>}
            </div>
          </div>
        </Card>
      )}
    </StepFrame>
  )
}
