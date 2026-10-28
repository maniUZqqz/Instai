import type { Strategy } from '../api/types'
import { useI18n } from '../i18n'
import { AreaField, Button, Card, NumberField, StringListField, TagsField, TextField } from './ui'

/** Editable view of a strategy proposal. Nothing here is saved by itself; the caller decides what to apply. */
export function StrategyEditor({ value, onChange }: { value: Strategy; onChange: (s: Strategy) => void }) {
  const { t } = useI18n()
  const set = (patch: Partial<Strategy>) => onChange({ ...value, ...patch })
  return (
    <div className="stack">
      <AreaField label={t('strat.positioning')} value={value.positioning} onChange={(v) => set({ positioning: v })} />
      <AreaField label={t('strat.audience_insight')} value={value.audience_insight} onChange={(v) => set({ audience_insight: v })} />
      <AreaField label={t('strat.tone')} value={value.tone_guidelines} onChange={(v) => set({ tone_guidelines: v })} />

      <Card title={t('strat.pillars')} soft>
        <div className="stack">
          {value.content_pillars.map((p, i) => (
            <div key={i} className="list-item">
              <div className="grow stack-sm">
                <TextField label={t('strat.pillar_title')} value={p.title} onChange={(v) => set({ content_pillars: value.content_pillars.map((x, j) => (j === i ? { ...x, title: v } : x)) })} />
                <AreaField label={t('strat.pillar_desc')} compact value={p.description} onChange={(v) => set({ content_pillars: value.content_pillars.map((x, j) => (j === i ? { ...x, description: v } : x)) })} />
              </div>
              <Button variant="ghost" size="sm" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => set({ content_pillars: value.content_pillars.filter((_, j) => j !== i) })} />
            </div>
          ))}
          <div>
            <Button size="sm" icon="plus" onClick={() => set({ content_pillars: [...value.content_pillars, { title: '', description: '' }] })}>
              {t('strat.add_pillar')}
            </Button>
          </div>
        </div>
      </Card>

      <Card title={t('strat.posting')} soft>
        <div className="grid-2">
          <NumberField
            label={t('strat.per_week')}
            min={1}
            max={21}
            value={value.posting_plan?.per_week}
            onChange={(v) => set({ posting_plan: { ...value.posting_plan, per_week: v ?? 1 } })}
          />
          <TagsField
            label={t('strat.best_times')}
            value={value.posting_plan?.best_times ?? []}
            onChange={(v) => set({ posting_plan: { ...value.posting_plan, best_times: v } })}
            placeholder={t('strat.best_times_ph')}
          />
        </div>
      </Card>

      <TagsField label={t('strat.hashtags')} value={value.hashtags} onChange={(v) => set({ hashtags: v })} ltr />
      <StringListField label={t('strat.risks')} value={value.risks ?? []} onChange={(v) => set({ risks: v })} addLabel={t('strat.add_risk')} />
    </div>
  )
}
