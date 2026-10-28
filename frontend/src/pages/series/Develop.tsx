import { useState } from 'react'
import { api } from '../../api/client'
import type { Development, DevStepState } from '../../api/types'
import { useToast } from '../../components/feedback'
import { Icon } from '../../components/Icon'
import { StylePicker, type Look } from '../../components/StylePicker'
import { Badge, Button, Card, CheckField, ErrorState, Loading, Notice } from '../../components/ui'
import { useAction, useQuery, useStored } from '../../hooks'
import { useI18n } from '../../i18n'
import { nm, useTemplates } from '../../library'
import { BibleStep } from './dev/BibleStep'
import { BrainstormStep } from './dev/BrainstormStep'
import { stepTitle, type StepProps } from './dev/common'
import { FactcheckStep, MapStep, ProfileStep, TimelineStep } from './dev/DataSteps'
import { CompositionStep, GateStep } from './dev/GateSteps'
import { ResearchStep } from './dev/ResearchStep'
import { SourceStep } from './dev/SourceStep'

const PANELS: Record<string, (p: StepProps) => JSX.Element> = {
  source: SourceStep,
  research: ResearchStep,
  brainstorm: BrainstormStep,
  profile: ProfileStep,
  map: MapStep,
  timeline: TimelineStep,
  factcheck: FactcheckStep,
  bible: BibleStep,
  composition: CompositionStep,
  gate: GateStep,
}

/** The development room of a series: the template's steps (source, research, brainstorm, map, bible, composition ...) and the approval gate. */
export default function Develop({ seriesId }: { seriesId: number }) {
  const { t, lang } = useI18n()
  const q = useQuery<Development>(`/series/${seriesId}/development`, { interval: (d) => (d && d.running_jobs.length ? 3000 : false) })
  const tpl = useTemplates()
  const [picked, setPicked] = useStored<string>('devstep.' + seriesId, '')
  const [look, setLook] = useState(false)
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Loading />
  const dev = q.data
  const firstOpen = dev.steps.find((s) => s.status !== 'done' && s.status !== 'skipped') ?? dev.steps[dev.steps.length - 1]
  const cur: DevStepState = dev.steps.find((s) => s.key === picked) ?? firstOpen
  const Panel = PANELS[cur.kind] ?? GateStep
  const doneN = dev.steps.filter((s) => s.status === 'done' || s.status === 'skipped').length
  const tmpl = tpl.byKey(dev.template.key) ?? dev.template
  const props: StepProps = { dev, step: cur, setDev: (d) => q.setData(d), reload: q.reload }
  return (
    <div className="stack">
      <div className="row between dev-head">
        <div className="row">
          <Badge tone="primary">{nm(tmpl as { name_fa: string; name_en: string }, lang)}</Badge>
          <Badge tone={dev.dev_status === 'approved' ? 'ok' : 'info'}>{t(('dev.st_' + (dev.dev_status === 'none' ? 'developing' : dev.dev_status)) as 'dev.st_developing')}</Badge>
          <span className="small muted">{t('dev.progress', { a: doneN, b: dev.steps.length })}</span>
          <span className="small muted">{t('dev.level', { level: t(('page.level.' + dev.automation_level) as 'page.level.manual') })}</span>
        </div>
        <Button size="sm" icon="palette" onClick={() => setLook((l) => !l)} aria-expanded={look}>{t('dev.look_title')}</Button>
      </div>
      {look && <LookCard dev={dev} setDev={(d) => q.setData(d)} onClose={() => setLook(false)} />}
      {dev.dev_status === 'approved' && <Notice tone="ok">{t('dev.approved_banner')}</Notice>}
      <div className="dev-room">
        <nav className="dev-stepper" aria-label={t('dev.steps')}>
          <ol>
            {dev.steps.map((s, i) => (
              <li key={s.key}>
                <button type="button" className={'dev-step st-' + s.status + (s.key === cur.key ? ' current' : '')} aria-current={s.key === cur.key ? 'step' : undefined} onClick={() => { setPicked(s.key); document.getElementById('dev-step-h')?.focus() }}>
                  <span className="num">{s.status === 'done' ? <Icon name="check" size={14} /> : i + 1}</span>
                  <span className="lbl">{stepTitle(s, lang)}</span>
                  <span className="small muted st">{t(('dev.status_' + s.status) as 'dev.status_todo')}{s.auto_approved && s.status === 'done' ? ' · ' + t('dev.auto') : ''}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <div className="dev-main" key={cur.key}>
          <Panel {...props} />
        </div>
      </div>
    </div>
  )
}

function LookCard({ dev, setDev, onClose }: { dev: Development; setDev: (d: Development) => void; onClose: () => void }) {
  const { t } = useI18n()
  const toast = useToast()
  const act = useAction()
  const [look, setLookState] = useState<Look>({ style_key: dev.look.style_key, realism: dev.look.realism, theme_key: dev.look.theme_key })
  const [langs, setLangs] = useState<string[]>(dev.languages)
  const save = async () => {
    const d = await act.run(() => api.patch<Development>(`/series/${dev.series.id}/development`, { look, languages: langs }), { success: t('common.saved') })
    if (d) setDev(d)
  }
  const inherit = async () => {
    const d = await act.run(() => api.patch<Development>(`/series/${dev.series.id}/development`, { look: {} }), { success: t('common.saved') })
    if (d) {
      setDev(d)
      setLookFrom(d)
    }
  }
  const setLookFrom = (d: Development) => setLookState({ style_key: d.look.style_key, realism: d.look.realism, theme_key: d.look.theme_key })
  const applyToPage = async () => {
    const r = await act.run(() => api.post(`/pages/${dev.series.page}/apply-look`, { style_key: look.style_key, theme_key: look.theme_key }))
    if (r) toast.ok(t('dev.look_applied'))
  }
  return (
    <Card title={t('dev.look_title')} actions={<Button size="sm" variant="ghost" onClick={onClose}>{t('common.close')}</Button>}>
      <div className="stack">
        <p className="small muted">{t('dev.look_note')}</p>
        {dev.look.inherited && <Notice tone="info">{t('dev.look_inherited')}</Notice>}
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field-label">{t('wiz.languages')}</legend>
          <div className="row">
            {(['fa', 'en'] as const).map((l) => (
              <CheckField key={l} label={l === 'fa' ? 'فارسی' : 'English'} checked={langs.includes(l)} onChange={(on) => setLangs(on ? [...langs, l] : langs.filter((x) => x !== l))} />
            ))}
          </div>
          <div className="field-hint">{t('dev.langs_note')}</div>
        </fieldset>
        <StylePicker value={look} onChange={setLookState} name="series-look" />
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={langs.length === 0} onClick={save}>{t('common.save')}</Button>
          <Button onClick={inherit} busy={act.busy}>{t('dev.look_inherit')}</Button>
          <Button onClick={applyToPage} busy={act.busy}>{t('dev.look_apply_page')}</Button>
        </div>
      </div>
    </Card>
  )
}
