import type { ReactNode } from 'react'
import { api } from '../../../api/client'
import type { DevStepState, Development, Job, StepStatus, TemplateStep } from '../../../api/types'
import { JobView } from '../../../components/domain'
import { Badge, Button, Notice, type Tone } from '../../../components/ui'
import { useAction } from '../../../hooks'
import { useI18n, type Lang } from '../../../i18n'

export interface StepProps {
  dev: Development
  step: DevStepState
  /** Replace the whole development payload (every status / data call returns it). */
  setDev: (d: Development) => void
  /** Refetch after a background job changed things on the server. */
  reload: () => void
}

export const stepTitle = (s: Pick<TemplateStep, 'title_fa' | 'title_en'>, lang: Lang) => (lang === 'fa' ? s.title_fa || s.title_en : s.title_en || s.title_fa)
export const stepHelp = (s: Pick<TemplateStep, 'help_fa' | 'help_en'>, lang: Lang) => (lang === 'fa' ? s.help_fa || s.help_en : s.help_en || s.help_fa)

const TONE: Record<StepStatus, Tone> = { todo: 'neutral', active: 'info', review: 'warn', done: 'ok', skipped: 'neutral' }
export function StepStatusBadge({ step }: { step: Pick<DevStepState, 'status' | 'auto_approved'> }) {
  const { t } = useI18n()
  return (
    <span className="row nw" style={{ gap: '0.25rem' }}>
      <Badge tone={TONE[step.status]}>{t(('dev.status_' + step.status) as 'dev.status_todo')}</Badge>
      {step.auto_approved && step.status === 'done' && <Badge tone="info">{t('dev.auto')}</Badge>}
    </span>
  )
}

/** A job shown with its title in the interface language (the server stores Persian titles; `job.kind.*` has both). */
export function LocalJob({ job, offline, onCancel }: { job: Job; offline?: boolean; onCancel?: () => void }) {
  const { tr } = useI18n()
  return <JobView job={{ ...job, title: tr('job.kind.' + job.kind, job.title) }} offline={offline} onCancel={onCancel} />
}

/** Title, help, status and the human gate buttons of one step; the step's own panel goes inside. */
export function StepFrame({ dev, step, setDev, children }: StepProps & { children: ReactNode }) {
  const { t, lang } = useI18n()
  const act = useAction()
  const setStatus = async (status: StepStatus) => {
    const d = await act.run(() => api.post<Development>(`/series/${dev.series.id}/dev/steps/${step.key}/status`, { status }), { success: status === 'done' ? t('dev.step_done_msg') : undefined })
    if (d) setDev(d)
  }
  const done = step.status === 'done'
  return (
    <section className="stack dev-panel" aria-labelledby="dev-step-h">
      <div className="row between">
        <div>
          <h2 id="dev-step-h" tabIndex={-1}>{stepTitle(step, lang)}</h2>
          {stepHelp(step, lang) && <p className="muted">{stepHelp(step, lang)}</p>}
        </div>
        <StepStatusBadge step={step} />
      </div>
      {children}
      {step.kind !== 'gate' && step.kind !== 'bible' && (
        <div className="row dev-gatebar">
          {!done && step.status !== 'skipped' && (
            <Button variant="primary" icon="check" busy={act.busy} disabled={!step.has_content} onClick={() => setStatus('done')}>
              {step.needs_human ? t('dev.approve_step') : t('dev.mark_done')}
            </Button>
          )}
          {(done || step.status === 'skipped') && <Button icon="refresh" busy={act.busy} onClick={() => setStatus('review')}>{t('dev.reopen')}</Button>}
          {!done && step.status !== 'skipped' && <Button variant="ghost" busy={act.busy} onClick={() => setStatus('skipped')}>{t('dev.skip')}</Button>}
          {!step.has_content && !done && <span className="small muted">{t('dev.needs_output')}</span>}
          {step.needs_human ? <span className="small muted">{t('dev.gate_human')}</span> : <span className="small muted">{t('dev.gate_auto')}</span>}
        </div>
      )}
      {act.error && <Notice tone="err">{act.error}</Notice>}
    </section>
  )
}

/** Detail fields of a brainstorm lens (mirrors instai/agents/studio_fake._DETAIL_KEYS). */
export const LENS_FIELDS: Record<string, string[]> = {
  divergence: ['divergence_moment', 'canon_outcome', 'changed_outcome', 'ripple_preview'],
  series_concept: ['hook', 'audience', 'story_engine'],
  scenario: ['setup', 'complication', 'payoff'],
  gag_format: ['gag', 'trigger', 'variation'],
  topic: ['why_it_is_hard', 'hook_question', 'common_misconception'],
  analogy: ['analogy', 'visual_metaphor', 'where_it_breaks_down'],
  character_concept: ['look', 'flaw', 'want'],
}

export function sourceLabel(dev: Development, id: number): string {
  return dev.sources.find((s) => s.id === id)?.title ?? `#${id}`
}

export function SourceBadges({ dev, ids }: { dev: Development; ids: number[] | undefined }) {
  const { t } = useI18n()
  if (!ids || ids.length === 0) return <Badge tone="warn">{t('dev.no_source')}</Badge>
  return (
    <span className="row" style={{ gap: '0.25rem' }}>
      {ids.map((i) => (
        <Badge key={i} tone="info" title={sourceLabel(dev, i)}>
          {t('dev.src_n', { n: i })}
        </Badge>
      ))}
    </span>
  )
}
