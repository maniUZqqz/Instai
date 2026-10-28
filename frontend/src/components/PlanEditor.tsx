import type { SeriesPlan } from '../api/types'
import { useI18n } from '../i18n'
import { AreaField, Button, Card, NumberField, SelectField, StringListField, TextField } from './ui'

/** Editable series plan proposal (arcs + episode plan). Nothing is saved until the owner applies it. */
export function PlanEditor({ value, onChange, withBranch }: { value: SeriesPlan; onChange: (p: SeriesPlan) => void; withBranch: boolean }) {
  const { t } = useI18n()
  const set = (patch: Partial<SeriesPlan>) => onChange({ ...value, ...patch })
  const arcs = value.arcs
  const removeArc = (i: number) => {
    const n = i + 1
    set({
      arcs: arcs.filter((_, j) => j !== i),
      episodes: value.episodes.map((e) => (e.arc === n ? { ...e, arc: undefined } : e.arc && e.arc > n ? { ...e, arc: e.arc - 1 } : e)),
    })
  }
  return (
    <div className="stack">
      <TextField label={t('wiz.series_title')} value={value.title} onChange={(v) => set({ title: v })} />
      <AreaField label={t('wiz.series_premise')} compact value={value.premise} onChange={(v) => set({ premise: v })} />
      {withBranch && (
        <>
          <AreaField label={t('wiz.series_branch')} compact value={value.branch_point ?? ''} onChange={(v) => set({ branch_point: v })} />
          <AreaField label={t('sb.alt_timeline')} compact value={value.alternative_timeline ?? ''} onChange={(v) => set({ alternative_timeline: v })} />
        </>
      )}
      <StringListField label={t('pf.content_rules')} value={value.content_rules ?? []} onChange={(v) => set({ content_rules: v })} addLabel={t('pf.add_rule')} />

      <Card title={t('sb.arcs')} soft>
        <div className="stack">
          {arcs.map((a, i) => (
            <div key={i} className="card flat stack-sm">
              <div className="row between">
                <span className="strong">{t('sb.arc_n', { n: i + 1 })}</span>
                <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => removeArc(i)} />
              </div>
              <TextField label={t('sb.arc_title')} value={a.title} onChange={(v) => set({ arcs: arcs.map((x, j) => (j === i ? { ...x, title: v } : x)) })} />
              <AreaField label={t('sb.arc_summary')} compact value={a.summary} onChange={(v) => set({ arcs: arcs.map((x, j) => (j === i ? { ...x, summary: v } : x)) })} />
              <div className="grid-2">
                <AreaField label={t('sb.goal')} compact value={a.goal ?? ''} onChange={(v) => set({ arcs: arcs.map((x, j) => (j === i ? { ...x, goal: v } : x)) })} />
                <AreaField label={t('sb.cliffhanger')} compact value={a.cliffhanger ?? ''} onChange={(v) => set({ arcs: arcs.map((x, j) => (j === i ? { ...x, cliffhanger: v } : x)) })} />
              </div>
            </div>
          ))}
          <div>
            <Button size="sm" icon="plus" onClick={() => set({ arcs: [...arcs, { title: '', summary: '' }] })}>
              {t('sb.add_arc')}
            </Button>
          </div>
        </div>
      </Card>

      <Card title={t('sb.eps_plan')} soft>
        <div className="stack">
          {value.episodes.map((e, i) => {
            const upd = (patch: Partial<(typeof value.episodes)[number]>) => set({ episodes: value.episodes.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
            return (
              <div key={i} className="card flat stack-sm">
                <div className="row between">
                  <span className="strong">{t('episode.number', { n: e.number })}</span>
                  <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => set({ episodes: value.episodes.filter((_, j) => j !== i) })} />
                </div>
                <div className="grid-3">
                  <NumberField label={t('sb.ep_number')} min={1} value={e.number} onChange={(v) => upd({ number: v ?? 1 })} />
                  <SelectField label={t('sb.ep_arc')} value={String(e.arc ?? '')} onChange={(v) => upd({ arc: v ? Number(v) : undefined })} options={[{ value: '', label: '—' }, ...arcs.map((a, j) => ({ value: String(j + 1), label: `${j + 1}. ${a.title || '…'}` }))]} />
                  <NumberField label={t('sb.ep_duration')} min={10} max={180} value={e.duration_sec} onChange={(v) => upd({ duration_sec: v ?? undefined })} />
                </div>
                <TextField label={t('sb.ep_title')} value={e.title} onChange={(v) => upd({ title: v })} />
                <AreaField label={t('sb.ep_logline')} compact value={e.logline} onChange={(v) => upd({ logline: v })} />
                <div className="grid-2">
                  <AreaField label={t('sb.goal')} compact value={e.goal ?? ''} onChange={(v) => upd({ goal: v })} />
                  <AreaField label={t('sb.cliffhanger')} compact value={e.cliffhanger ?? ''} onChange={(v) => upd({ cliffhanger: v })} />
                </div>
              </div>
            )
          })}
          <div>
            <Button size="sm" icon="plus" onClick={() => set({ episodes: [...value.episodes, { number: Math.max(0, ...value.episodes.map((x) => x.number)) + 1, title: '', logline: '' }] })}>
              {t('sb.add_episode')}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
