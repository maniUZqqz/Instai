import { api } from '../../../api/client'
import type { Development, SeriesDetail } from '../../../api/types'
import { ErrorState, Loading, Badge, Button, Card, LinkButton, Notice } from '../../../components/ui'
import { useAction, useQuery } from '../../../hooks'
import { useI18n } from '../../../i18n'
import { PlanTab } from '../../SeriesBuilder'
import { StepFrame, StepStatusBadge, stepTitle, type StepProps } from './common'

export function CompositionStep(p: StepProps) {
  const { t } = useI18n()
  const { dev, reload } = p
  const q = useQuery<SeriesDetail>(`/series/${dev.series.id}`)
  return (
    <StepFrame {...p}>
      {dev.bible.status !== 'approved' && <Notice tone="warn">{t('comp.need_bible')}</Notice>}
      <Card title={t('comp.current')}>
        {q.error && !q.data ? <ErrorState error={q.error} onRetry={q.reload} /> : !q.data ? <Loading /> : (
          <div className="stack-sm">
            <div className="row">
              <Badge>{t('series.episodes_n', { n: q.data.episodes.length })}</Badge>
              <Badge>{t('comp.arcs_n', { n: q.data.arcs.length })}</Badge>
              <LinkButton size="sm" to={`/series/${dev.series.id}#episodes`} icon="film">{t('comp.edit_episodes')}</LinkButton>
            </div>
            {q.data.episodes.length > 0 && (
              <ol className="small steps-list">{q.data.episodes.map((e) => <li key={e.id}>{e.title}{e.logline ? <span className="muted"> — {e.logline}</span> : null}</li>)}</ol>
            )}
          </div>
        )}
      </Card>
      {q.data && (
        <PlanTab
          s={q.data}
          isAnime={dev.template.base_format === 'anime_whatif'}
          onApplied={(d) => { q.setData(d); reload() }}
        />
      )}
    </StepFrame>
  )
}

export function GateStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, setDev } = p
  const act = useAction()
  const others = dev.steps.filter((s) => s.kind !== 'gate')
  const bibleOk = dev.bible.status === 'approved'
  const planOk = dev.has_plan
  const approved = dev.dev_status === 'approved'
  const approve = async () => {
    const d = await act.run(() => api.post<Development>(`/series/${dev.series.id}/development/approve`, {}), { success: t('gate.approved_msg') })
    if (d) setDev(d)
  }
  const reopen = async () => {
    const d = await act.run(() => api.post<Development>(`/series/${dev.series.id}/development/reopen`, {}))
    if (d) setDev(d)
  }
  return (
    <StepFrame {...p}>
      <Card title={t('gate.checklist')}>
        <ul className="plain-list stack-sm">
          {others.map((s) => (
            <li key={s.key} className="row between">
              <span>{stepTitle(s, lang)}</span>
              <StepStatusBadge step={s} />
            </li>
          ))}
          <li className="row between"><span>{t('gate.bible_ok')}</span><Badge tone={bibleOk ? 'ok' : 'warn'}>{bibleOk ? t('gate.yes') : t('gate.no')}</Badge></li>
          <li className="row between"><span>{t('gate.plan_ok')}</span><Badge tone={planOk ? 'ok' : 'warn'}>{planOk ? t('gate.yes') : t('gate.no')}</Badge></li>
        </ul>
      </Card>
      {approved ? (
        <Notice tone="ok">
          <div className="stack-sm">
            <div className="strong">{t('gate.done_title')}</div>
            <div>{t('gate.done_text')}</div>
            <div className="row">
              <LinkButton variant="primary" to={`/series/${dev.series.id}#episodes`} icon="film">{t('gate.go_episodes')}</LinkButton>
              <Button icon="refresh" busy={act.busy} onClick={reopen}>{t('gate.reopen')}</Button>
            </div>
          </div>
        </Notice>
      ) : (
        <div className="row dev-gatebar">
          <Button variant="primary" icon="flag" busy={act.busy} disabled={!bibleOk || !planOk} onClick={approve}>{t('gate.approve')}</Button>
          <span className="small muted">{t('gate.human_note')}</span>
        </div>
      )}
    </StepFrame>
  )
}
