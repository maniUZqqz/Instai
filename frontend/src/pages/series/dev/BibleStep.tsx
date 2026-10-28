import { useEffect, useState } from 'react'
import { api } from '../../../api/client'
import type { Bible, BibleCharacter, BibleData, Development } from '../../../api/types'
import { useToast } from '../../../components/feedback'
import { AreaField, Badge, Button, Card, CheckField, Notice, NumberField, StringListField, SwitchField, TextField } from '../../../components/ui'
import { useAction, useJobRunner } from '../../../hooks'
import { useI18n } from '../../../i18n'
import { LocalJob, StepFrame, type StepProps } from './common'

const blankChar = (): BibleCharacter => ({ name: '', role: '', appearance: '', personality: '', motivations: '', abilities: '', is_original: true })

export function BibleStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, step, setDev } = p
  const toast = useToast()
  const bible = dev.bible
  const [d, setD] = useState<BibleData>(bible.data)
  useEffect(() => setD(bible.data), [JSON.stringify(bible.data), bible.version]) // eslint-disable-line react-hooks/exhaustive-deps
  const [instruction, setInstruction] = useState('')
  const [keep, setKeep] = useState(false)
  const act = useAction()
  const runner = useJobRunner({ onSucceeded: () => api.get<Development>(`/series/${dev.series.id}/development`).then(setDev) })
  const dirty = JSON.stringify(d) !== JSON.stringify(bible.data)
  const set = (patch: Partial<BibleData>) => setD((x) => ({ ...x, ...patch }))
  const updChar = (i: number, patch: Partial<BibleCharacter>) => set({ characters: d.characters.map((c, j) => (j === i ? { ...c, ...patch } : c)) })
  const updArc = (i: number, patch: Partial<BibleData['arcs'][number]>) => set({ arcs: d.arcs.map((a, j) => (j === i ? { ...a, ...patch } : a)) })
  const refresh = async () => setDev(await api.get<Development>(`/series/${dev.series.id}/development`))
  const save = async () => {
    const r = await act.run(() => api.put<Bible>(`/series/${dev.series.id}/bible`, { data: d }), { success: t('common.saved') })
    if (r) await refresh()
  }
  const approve = async () => {
    if (dirty) await api.put(`/series/${dev.series.id}/bible`, { data: d }).catch(() => undefined)
    const r = await act.run(() => api.post<{ bible: Bible; synced: { characters_added: number } }>(`/series/${dev.series.id}/bible/approve`, {}))
    if (r) {
      toast.ok(t('bible.approved_msg', { n: r.synced.characters_added }))
      await refresh()
    }
  }
  const revoke = async () => {
    if (await act.run(() => api.post(`/series/${dev.series.id}/bible/revoke`, {}))) await refresh()
  }
  const isWhatIf = dev.template.base_format === 'anime_whatif' || !!d.branch_point
  const approved = bible.status === 'approved'
  return (
    <StepFrame {...p}>
      <Card title={t('bible.generate_title')}>
        <div className="stack">
          <p className="small muted">{t('bible.intro')}</p>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <TextField className="grow" label={t('idea.instruction')} value={instruction} onChange={setInstruction} placeholder={t('bible.instruction_ph')} />
            <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} onClick={() => runner.start(() => api.post(`/series/${dev.series.id}/bible/generate`, { instruction, keep_existing: keep, language: lang }))}>
              {bible.exists ? t('bible.regenerate') : t('bible.generate')}
            </Button>
          </div>
          {bible.exists && <CheckField label={t('bible.keep')} hint={t('bible.keep_hint')} checked={keep} onChange={setKeep} />}
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
        </div>
      </Card>

      <Card title={t('bible.doc')} actions={<span className="row"><Badge tone={approved ? 'ok' : 'warn'}>{approved ? t('bible.st_approved') : t('bible.st_draft')}</Badge>{bible.exists && <Badge>{t('bible.version', { n: bible.version })}</Badge>}</span>}>
        <div className="stack">
          {approved && <Notice tone="ok">{t('bible.approved_note')}</Notice>}
          <div className="grid-2">
            <TextField label={t('bible.title')} value={d.title} onChange={(v) => set({ title: v })} />
            <TextField label={t('bible.tone')} value={d.tone} onChange={(v) => set({ tone: v })} />
          </div>
          <AreaField label={t('bible.logline')} compact value={d.logline} onChange={(v) => set({ logline: v })} />
          <AreaField label={t('bible.premise')} value={d.premise} onChange={(v) => set({ premise: v })} required />
          {isWhatIf && (
            <div className="grid-2">
              <AreaField label={t('wiz.series_branch')} compact value={d.branch_point} onChange={(v) => set({ branch_point: v })} />
              <AreaField label={t('sb.alt_timeline')} compact value={d.alternative_timeline} onChange={(v) => set({ alternative_timeline: v })} />
            </div>
          )}
          <StringListField label={t('bible.world_rules')} value={d.world_rules} onChange={(v) => set({ world_rules: v })} addLabel={t('bible.add_rule')} />
          <StringListField label={t('bible.themes')} value={d.themes} onChange={(v) => set({ themes: v })} addLabel={t('bible.add_theme')} rows={1} />

          <h3>{t('bible.characters')}</h3>
          {d.characters.map((c, i) => (
            <div key={i} className="card soft flat stack-sm">
              <div className="row between"><strong>{c.name || t('wiz.char_n', { n: i + 1 })}</strong><Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => set({ characters: d.characters.filter((_, j) => j !== i) })} /></div>
              <div className="grid-2">
                <TextField label={t('char.name')} value={c.name} onChange={(v) => updChar(i, { name: v })} />
                <TextField label={t('char.role')} value={c.role} onChange={(v) => updChar(i, { role: v })} />
              </div>
              <AreaField label={t('char.appearance')} compact value={c.appearance} onChange={(v) => updChar(i, { appearance: v })} />
              <div className="grid-2">
                <AreaField label={t('char.personality')} compact value={c.personality} onChange={(v) => updChar(i, { personality: v })} />
                <AreaField label={t('char.motivations')} compact value={c.motivations} onChange={(v) => updChar(i, { motivations: v })} />
              </div>
              <AreaField label={t('char.abilities')} compact value={c.abilities} onChange={(v) => updChar(i, { abilities: v })} />
              <SwitchField label={t('char.original')} checked={c.is_original} onChange={(v) => updChar(i, { is_original: v })} />
            </div>
          ))}
          <div><Button icon="plus" onClick={() => set({ characters: [...d.characters, blankChar()] })}>{t('wiz.add_char')}</Button></div>

          <h3>{t('bible.arcs')}</h3>
          {d.arcs.map((a, i) => (
            <div key={i} className="card soft flat stack-sm">
              <div className="row between"><strong>{t('sb.arc_n', { n: i + 1 })}</strong><Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => set({ arcs: d.arcs.filter((_, j) => j !== i) })} /></div>
              <TextField label={t('sb.arc_title')} value={a.title} onChange={(v) => updArc(i, { title: v })} />
              <AreaField label={t('sb.arc_summary')} compact value={a.summary} onChange={(v) => updArc(i, { summary: v })} />
              <div className="grid-2">
                <AreaField label={t('sb.goal')} compact value={a.goal} onChange={(v) => updArc(i, { goal: v })} />
                <AreaField label={t('sb.cliffhanger')} compact value={a.cliffhanger} onChange={(v) => updArc(i, { cliffhanger: v })} />
              </div>
            </div>
          ))}
          <div><Button icon="plus" onClick={() => set({ arcs: [...d.arcs, { title: '', summary: '', goal: '', cliffhanger: '' }] })}>{t('sb.add_arc')}</Button></div>

          <div className="grid-2">
            <NumberField label={t('wiz.episodes')} min={1} max={60} value={d.episode_count} onChange={(v) => set({ episode_count: v ?? 5 })} />
            <NumberField label={t('wiz.length')} min={10} max={180} value={d.episode_length_sec} onChange={(v) => set({ episode_length_sec: v ?? 45 })} />
          </div>
          <AreaField label={t('bible.visual_notes')} compact value={d.visual_notes} onChange={(v) => set({ visual_notes: v })} hint={t('bible.visual_hint')} />
          <StringListField label={t('pf.content_rules')} value={d.content_rules} onChange={(v) => set({ content_rules: v })} addLabel={t('pf.add_rule')} />
          <Notice tone="info">{t('bible.sync_note')}</Notice>
          <div className="row dev-gatebar">
            <Button icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('common.save')}</Button>
            {!approved ? (
              <Button variant="primary" icon="check" busy={act.busy} disabled={!d.premise.trim()} onClick={approve}>{t('bible.approve')}</Button>
            ) : (
              <Button icon="refresh" busy={act.busy} onClick={revoke}>{t('bible.revoke')}</Button>
            )}
            {step.needs_human ? <span className="small muted">{t('dev.gate_human')}</span> : <span className="small muted">{t('dev.gate_auto')}</span>}
          </div>
        </div>
      </Card>
    </StepFrame>
  )
}
