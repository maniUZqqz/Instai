import { Player } from '@remotion/player'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { JobView } from '../components/domain'
import { Badge, Button, Notice, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { ScenePlan, planMeta } from '../../../remotion/src/components/ScenePlan'
import { COMPONENT_DEFS } from '../../../remotion/src/components/defs'
import type { StyleKit } from '../../../remotion/src/kit/theme'
import type { MotionPlanDto, MotionRound, MotionShotState } from './types'

/** the label of a component of the plan in the UI language */
const labelOf = (type: string, lang: 'fa' | 'en') => {
  const d = COMPONENT_DEFS.find((c) => c.type === type)
  return d ? (lang === 'en' ? d.en : d.fa) : type
}

function Frames({ rows, title }: { rows: { scene: number; image_rel: string }[]; title: string }) {
  const shown = rows.filter((r) => r.image_rel)
  if (!shown.length) return null
  return (
    <div className="stack-sm">
      <span className="small muted">{title}</span>
      <div className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
        {shown.map((r, i) => <img key={i} src={'/media/' + r.image_rel + '?v=' + r.scene} alt="" loading="lazy" style={{ height: 96, borderRadius: 6, border: '1px solid rgba(128,128,128,.35)' }} />)}
      </div>
    </div>
  )
}

function Rounds({ rounds, lang }: { rounds: MotionRound[]; lang: 'fa' | 'en' }) {
  const { t } = useI18n()
  return (
    <div className="stack-sm" data-testid="mp-critique-rounds">
      {rounds.map((r) => (
        <div key={r.n} className="stack-sm" style={{ borderInlineStart: '3px solid rgba(128,128,128,.35)', paddingInlineStart: '0.6rem' }}>
          <div className="row" style={{ gap: '0.5rem', flexWrap: 'wrap' }}>
            <span className="strong">{t('mp.round', { n: r.n })}</span>
            <Badge tone={r.verdict === 'ok' ? 'ok' : 'warn'}>{r.verdict === 'ok' ? t('mp.verdict_ok') : t('mp.verdict_fix')}</Badge>
            {r.applied.length > 0 && <Badge tone="info">{t('mp.applied', { n: r.applied.length })}</Badge>}
            {r.rejected.length > 0 && <Badge tone="neutral">{t('mp.rejected', { n: r.rejected.length })}</Badge>}
          </div>
          {r.issues.map((i, k) => <p key={k} className="small" dir="auto">{t('mp.scene_n', { n: i.scene + 1 })}: {i.problem}</p>)}
          <Frames rows={r.before} title={t('mp.before')} />
          <Frames rows={r.after} title={t('mp.after')} />
          {r.rejected.map((x, k) => <p key={'r' + k} className="small muted" dir="auto">{lang === 'en' ? x.why_en : x.why}</p>)}
        </div>
      ))}
    </div>
  )
}

/** The scene plan of ONE motion-graphics shot, inside the storyboard: its scenes, a live preview in the series' own look, a request box («make the title bigger»),
 *  the versions (undo / redo), the checks on real frames and the visual critique by the vision model. */
export function MotionPlanBlock({ shotId, editable, dirty }: { shotId: number; editable: boolean; dirty: boolean }) {
  const { t, tr, lang } = useI18n()
  const act = useAction()
  const runner = useJobRunner({ onFinished: () => q.reload() })
  const [ask, setAsk] = useState('')
  const [said, setSaid] = useState('')
  const q = useQuery<MotionShotState>(`/shots/${shotId}/motion`, { interval: (d) => (d && d.plan && d.plan.critique?.state === 'running' ? 4000 : false) })
  const st = q.data
  const plan: MotionPlanDto | null = st?.plan ?? null
  const spec = plan?.spec
  const meta = useMemo(() => (st && spec ? planMeta({ kit: st.kit as unknown as StyleKit, size: st.size, spec: spec as any }) : null), [st, spec])
  const props = useMemo(() => (st && spec ? { kit: st.kit as unknown as StyleKit, size: st.size, spec: spec as any, fontBase: 'page' } : null), [st, spec])

  const job = (action: 'write' | 'qa' | 'critique', success: string) =>
    void act.run(() => runner.start(() => api.post(`/shots/${shotId}/motion`, { action, force: true })), { success })
  const patch = () =>
    plan &&
    void act.run(async () => {
      const r = await api.post<{ plan: MotionPlanDto; applied: boolean; say: string }>(`/motion/plans/${plan.id}/patch`, { request: ask, lang })
      setSaid(r.say)
      if (r.applied) setAsk('')
      q.reload()
    })
  const step = (what: 'undo' | 'redo') =>
    plan &&
    void act.run(async () => {
      await api.post(`/motion/plans/${plan.id}/${what}`, {})
      q.reload()
    })
  const portrait = !!meta && meta.height > meta.width
  const qaRep = plan?.qa
  const remaining = qaRep?.remaining ?? []

  return (
    <div className="stack-sm" data-testid="mp-block" style={{ border: '1px solid rgba(128,128,128,.3)', borderRadius: 10, padding: '0.75rem' }}>
      <div className="row between" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
        <span className="strong">{t('mp.title')}</span>
        <span className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
          {plan && <Badge tone={plan.origin === 'ai' ? 'info' : 'neutral'}>{plan.origin === 'ai' ? t('mp.origin_ai') : plan.origin === 'fallback' ? t('mp.origin_fallback') : t('mp.origin_user')}</Badge>}
          {st?.edited && <Badge tone="primary">{t('mp.edited')}</Badge>}
          {st?.stale && !st.edited && <Badge tone="warn" title={t('mp.stale_hint')}>{t('mp.stale')}</Badge>}
          {st?.clip && <Badge tone={st.clip.current ? 'ok' : 'warn'}>{st.clip.current ? t('mp.clip_ok') : t('mp.clip_old')}</Badge>}
        </span>
      </div>
      <p className="small muted">{t('mp.intro')}</p>
      {!st && <p className="small muted">…</p>}
      {st && !st.narration_ready && <Notice tone="info" icon="clock">{t('mp.wait_narration')}</Notice>}
      {st && !plan && <Notice tone="info" icon="info">{t('mp.no_plan')}</Notice>}
      {plan && spec && (
        <div className="grid-2" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(14rem, 1fr))', gap: '0.75rem', alignItems: 'start' }}>
          <div className="stack-sm">
            <div className="row" style={{ gap: '0.3rem', flexWrap: 'wrap' }} data-testid="mp-scenes">
              {spec.scenes.map((s, i) => <Badge key={i} tone="neutral">{i + 1}. {labelOf(String(s.type), lang)} · {Number(s.duration).toFixed(1)}s</Badge>)}
            </div>
            <p className="small muted">{t('mp.total', { x: Number(spec.total_s ?? 0).toFixed(1), y: st?.seconds.toFixed(1) ?? '' })} · {t('mp.style', { x: (lang === 'en' ? st?.kit.name_en : st?.kit.name_fa) || st?.kit.name || '' })}</p>
            {editable && (
              <>
                <TextField label={t('mp.ask')} value={ask} onChange={setAsk} dir="auto" placeholder={t('mp.ask_ph')} disabled={dirty} data-testid="mp-ask" />
                <div className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
                  <Button size="sm" icon="spark" busy={act.busy} disabled={!ask.trim() || dirty} onClick={patch} data-testid="mp-apply">{t('mp.apply')}</Button>
                  <Button size="sm" icon="prev" disabled={!plan.can_undo || act.busy} onClick={() => step('undo')} data-testid="mp-undo">{t('mp.undo')}</Button>
                  <Button size="sm" icon="next" disabled={!plan.can_redo || act.busy} onClick={() => step('redo')} data-testid="mp-redo">{t('mp.redo')}</Button>
                </div>
                {said && <p className="small" dir="auto" data-testid="mp-said">{said}</p>}
              </>
            )}
            {plan.history && plan.history.length > 1 && (
              <details>
                <summary className="small">{t('mp.versions', { n: plan.history.length })}</summary>
                <ol className="small" style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                  {plan.history.map((h) => <li key={h.n} style={{ fontWeight: h.current ? 700 : 400 }} dir="auto">{h.label} <span className="muted">({tr('mp.src.' + h.source, h.source)})</span></li>)}
                </ol>
              </details>
            )}
          </div>
          <div dir="ltr" data-testid="mp-player" style={{ width: '100%', maxWidth: portrait ? 200 : 360, margin: '0 auto' }}>
            {props && meta && (
              <Player
                key={plan.id + ':' + plan.rev}
                component={ScenePlan as any}
                inputProps={props}
                durationInFrames={meta.durationInFrames}
                compositionWidth={meta.width}
                compositionHeight={meta.height}
                fps={meta.fps}
                initialFrame={Math.min(60, meta.durationInFrames - 1)}
                controls
                loop
                clickToPlay
                acknowledgeRemotionLicense
                style={{ width: '100%', borderRadius: 8, overflow: 'hidden' }}
              />
            )}
          </div>
        </div>
      )}
      {plan && qaRep && (qaRep.rounds || qaRep.remaining) && (
        <div className="stack-sm" data-testid="mp-qa">
          <div className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
            <Badge tone={remaining.length ? 'warn' : 'ok'}>{remaining.length ? t('mp.qa_left', { n: remaining.length }) : t('mp.qa_ok')}</Badge>
            {!!qaRep.fixed && <Badge tone="info">{t('mp.qa_fixed', { n: qaRep.fixed })}</Badge>}
            <Badge tone={qaRep.geometry ? 'ok' : 'neutral'}>{qaRep.geometry ? t('mp.qa_frames') : t('mp.qa_rules_only')}</Badge>
          </div>
          {remaining.map((f, i) => <p key={i} className="small" dir="auto">{lang === 'en' ? f.message_en : f.message}</p>)}
        </div>
      )}
      {plan && plan.critique?.state && (
        <div className="stack-sm" data-testid="mp-critique">
          <Notice tone={plan.critique.state === 'unavailable' ? 'warn' : 'info'} icon={plan.critique.state === 'running' ? 'clock' : 'info'}><span dir="auto">{lang === 'en' ? plan.critique.message_en : plan.critique.message}</span></Notice>
          {plan.critique.rounds && plan.critique.rounds.length > 0 && <Rounds rounds={plan.critique.rounds} lang={lang} />}
        </div>
      )}
      {runner.job && <JobView job={runner.job} offline={runner.offline} compact />}
      {editable && (
        <div className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
          <Button size="sm" icon="refresh" busy={act.busy || runner.busy} disabled={dirty || !st} onClick={() => job('write', t('mp.write_started'))} data-testid="mp-write">{plan ? t('mp.rewrite') : t('mp.write')}</Button>
          <Button size="sm" icon="check" busy={runner.busy} disabled={!plan || dirty} onClick={() => job('qa', t('mp.qa_started'))} data-testid="mp-qa-run">{t('mp.qa_run')}</Button>
          <Button size="sm" icon="star" busy={runner.busy} disabled={!plan || dirty} onClick={() => job('critique', t('mp.critique_started'))} data-testid="mp-critique-run" title={t('mp.critique_hint')}>{t('mp.critique_run')}</Button>
        </div>
      )}
    </div>
  )
}
