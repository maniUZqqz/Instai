import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Episode, EpisodeState, Job, PageDetail, Script } from '../api/types'
import { STATE_ORDER } from '../api/types'
import { useConfirm, useToast } from '../components/feedback'
import { BUSY_STATES, ErrorText, JobView, StateBadge } from '../components/domain'
import { Badge, Button, Card, Empty, ErrorState, LinkButton, Loading, Notice, PageHead, Tabs, TextField } from '../components/ui'
import { EXPLAINER } from '../formats'
import { useAction, useHashTabOpt, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { Production, activeProdJobs } from './episode/Production'
import { Events, Research, Versions } from './episode/Research'
import { ScriptEditor } from './episode/ScriptEditor'
import { StoryboardEditor } from './episode/StoryboardEditor'
import { Studio } from './episode/Studio'

const TABS = ['script', 'storyboard', 'studio', 'production', 'research', 'versions', 'events'] as const
type Tab = (typeof TABS)[number]
const isActive = (j: Job) => j.status === 'queued' || j.status === 'running'

function defaultTab(s: EpisodeState): Tab {
  if (['draft', 'planned', 'scripting', 'script_review'].includes(s)) return 'script'
  if (s === 'storyboarding') return 'storyboard'
  return 'production'
}

export default function EpisodeEditor() {
  const { t, f } = useI18n()
  const { id } = useParams()
  const toast = useToast()
  const q = useQuery<Episode>(`/episodes/${id}`, { interval: (e) => (e && (BUSY_STATES.includes(e.state) || e.jobs.some(isActive)) ? 2000 : false) })
  const page = useQuery<PageDetail>(q.data ? `/pages/${q.data.page}` : null)
  const [hashTab, setTab] = useHashTabOpt(TABS)
  const [rev, setRev] = useState(0)
  const [scriptDirty, setScriptDirty] = useState(false)
  const seen = useRef(new Map<number, string>())
  const ep = q.data
  useTitle(ep ? ep.title || t('episode.untitled', { n: ep.number }) : undefined)

  // When a background job ends, rebuild the editors from the server copy (new script / storyboard / media).
  useEffect(() => {
    if (!ep) return
    let finished = false
    for (const j of ep.jobs) {
      const prev = seen.current.get(j.id)
      if (prev && (prev === 'queued' || prev === 'running') && !isActive(j)) {
        finished = true
        if (j.status === 'failed') toast.err(`${j.title}: ${j.error || t('job.failed')}`)
      }
      seen.current.set(j.id, j.status)
    }
    if (finished) setRev((r) => r + 1)
  }, [ep?.jobs]) // eslint-disable-line react-hooks/exhaustive-deps

  // Workaround: pipeline.advance() counts the finishing job itself as "still running", so after the last image/voice job the
  // episode can sit in asset_generation with nothing queued. Pressing "produce" again is idempotent and continues the chain,
  // so do it once per finished job (the owner already asked for this production run).
  const continued = useRef<number>(0)
  useEffect(() => {
    if (!ep || !['asset_generation', 'animation', 'assembly'].includes(ep.state)) return
    const prod = ep.jobs.filter((j) => j.kind.startsWith('prod.'))
    if (prod.length === 0 || ep.jobs.some(isActive) || prod[0].status !== 'succeeded' || continued.current === prod[0].id) return
    const id = prod[0].id
    const mode = (prod[0].payload?.mode as string) === 'final' ? 'final' : 'preview'
    const timer = window.setTimeout(() => {
      continued.current = id
      api.post(`/episodes/${ep.id}/produce`, { mode }).then(() => q.reload()).catch(() => undefined)
    }, 1500)
    return () => window.clearTimeout(timer)
  }, [ep]) // eslint-disable-line react-hooks/exhaustive-deps

  if (q.error && !ep) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!ep) return <Loading />

  const isExplainer = ep.page_format === EXPLAINER
  const tabs = TABS.filter((k) => k !== 'research' || isExplainer)
  const tab: Tab = hashTab && tabs.includes(hashTab) ? hashTab : defaultTab(ep.state)
  const labels: Record<Tab, string> = { script: t('ed.tab_script'), storyboard: t('ed.tab_storyboard'), studio: t('ed.tab_studio'), production: t('ed.tab_production'), research: t('ed.tab_research'), versions: t('ed.tab_versions'), events: t('ed.tab_events') }
  const characters = page.data?.characters ?? []
  const shots = ep.scenes.flatMap((s) => s.shots)
  const hasMedia = shots.some((s) => s.keyframe || s.narration_asset)
  const jobsActive = ep.jobs.some(isActive)
  const prodActive = activeProdJobs(ep).length > 0
  const scriptEditable = ['draft', 'planned', 'script_review', 'storyboarding'].includes(ep.state)
  const boardEditable = ['storyboarding', 'asset_generation', 'quality_review', 'ready_for_approval'].includes(ep.state) && !prodActive
  const speakers = Array.from(new Set([t('script.narrator'), ...characters.map((c) => c.name)]))
  const crumbs = [
    { label: t('nav.pages'), to: '/pages' },
    { label: page.data?.name ?? '…', to: `/pages/${ep.page}` },
    { label: ep.series_title, to: `/series/${ep.series}` },
    { label: t('episode.number', { n: ep.number }) },
  ]
  const refresh = () => q.reload()
  const rebuild = () => {
    setRev((r) => r + 1)
    q.reload()
  }

  return (
    <div className="stack">
      <PageHead title={ep.title || t('episode.untitled', { n: ep.number })} crumbs={crumbs}>
        <div className="row">
          <StateBadge state={ep.state} label={ep.state_label} />
          <span className="muted small">{t('episode.number', { n: ep.number })} · {f.duration(ep.duration_sec)}</span>
        </div>
      </PageHead>
      <TitleEditor ep={ep} onSaved={refresh} />
      {(ep.logline || ep.goal || ep.cliffhanger) && (
        <Card soft>
          <dl className="kv small">
            {ep.logline && (<><dt>{t('sb.ep_logline')}</dt><dd>{ep.logline}</dd></>)}
            {ep.goal && (<><dt>{t('sb.goal')}</dt><dd>{ep.goal}</dd></>)}
            {ep.cliffhanger && (<><dt>{t('sb.cliffhanger')}</dt><dd>{ep.cliffhanger}</dd></>)}
          </dl>
        </Card>
      )}

      <Stepper ep={ep} onChanged={rebuild} />
      <NextStep ep={ep} hasShots={shots.length > 0} scriptDirty={scriptDirty} isExplainer={isExplainer} setTab={setTab} onChanged={refresh} onRebuild={rebuild} onEpisode={(e) => { q.setData(e); rebuild() }} jobsActive={jobsActive} />

      <Tabs tabs={tabs.map((k) => ({ key: k, label: labels[k] }))} value={tab} onChange={setTab} label={t('ed.tabs')} />

      {tab === 'script' && (
        <ScriptEditor
          key={'s' + rev}
          ep={ep}
          characters={characters}
          editable={scriptEditable}
          onDirty={setScriptDirty}
          onSaved={(e) => { q.setData(e); rebuild() }}
          rewriteBusy={ep.state === 'scripting'}
          onRewrite={async () => { await api.post(`/episodes/${ep.id}/generate-script`, {}).catch((e) => toast.err(e.message)); refresh() }}
          onUnlock={async () => { await api.post(`/episodes/${ep.id}/transition`, { to: 'script_review', reason: 'edit script' }).catch((e) => toast.err(e.message)); rebuild() }}
        />
      )}
      {tab === 'storyboard' &&
        (ep.scenes.length === 0 ? (
          <Empty icon="film" title={t('sbd.empty_title')} text={ep.state === 'storyboarding' ? t('sbd.empty_text') : t('sbd.empty_text_early')} />
        ) : (
          <StoryboardEditor
            key={'b' + rev}
            ep={ep}
            page={page.data}
            speakers={speakers}
            editable={boardEditable}
            structureEditable={boardEditable}
            hasMedia={hasMedia}
            onSavedEp={(e) => { q.setData(e); rebuild() }}
            onChanged={refresh}
            onRegenerate={refresh}
          />
        ))}
      {tab === 'studio' && <Studio ep={ep} page={page.data} onChanged={refresh} />}
      {tab === 'production' && <Production ep={ep} page={page.data} onChanged={refresh} onProduced={refresh} />}
      {tab === 'research' && isExplainer && <Research ep={ep} onChanged={refresh} />}
      {tab === 'versions' && <Versions ep={ep} onRestored={(e) => { q.setData(e); rebuild() }} />}
      {tab === 'events' && <Events ep={ep} />}
    </div>
  )
}

// ---------------------------------------------------------------- title
function TitleEditor({ ep, onSaved }: { ep: Episode; onSaved: () => void }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [v, setV] = useState(ep.title)
  const act = useAction()
  if (!open) {
    return (
      <div>
        <Button size="sm" variant="ghost" icon="edit" onClick={() => { setV(ep.title); setOpen(true) }}>{t('ed.edit_title')}</Button>
      </div>
    )
  }
  return (
    <div className="row" style={{ alignItems: 'flex-end' }}>
      <TextField className="grow" label={t('sb.ep_title')} value={v} onChange={setV} autoFocus />
      <Button variant="primary" busy={act.busy} disabled={!v.trim()} onClick={async () => { const r = await act.run(async () => { await api.patch(`/episodes/${ep.id}`, { title: v.trim() }); return true }, { success: t('common.saved') }); if (r) { setOpen(false); onSaved() } }}>{t('common.save')}</Button>
      <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
    </div>
  )
}

// ---------------------------------------------------------------- state machine stepper
function Stepper({ ep, onChanged }: { ep: Episode; onChanged: () => void }) {
  const { t, tr } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const failed = ep.state === 'failed'
  const cur = failed ? STATE_ORDER.indexOf((ep.failed_state || 'planned') as EpisodeState) : STATE_ORDER.indexOf(ep.state)
  const allowed = new Set(ep.allowed_next.map((a) => a.state))
  const canJump = (s: EpisodeState, i: number) => allowed.has(s) && i < cur && !['draft', 'planned', 'scripting'].includes(s)
  const jump = async (s: EpisodeState) => {
    if (!(await confirm({ message: t('ed.jump_confirm', { state: tr('state.' + s, s) }), confirmLabel: t('ed.jump') }))) return
    const r = await act.run(async () => { await api.post(`/episodes/${ep.id}/transition`, { to: s, reason: 'manual (stepper)' }); return true })
    if (r) onChanged()
  }
  return (
    <nav aria-label={t('ed.stepper')}>
      <ol className="state-steps" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {ep.state === 'cancelled' && (
          <li><span className="state-step failed">{t('state.cancelled')}</span></li>
        )}
        {STATE_ORDER.map((s, i) => {
          const cls = 'state-step' + (i < cur ? ' done' : i === cur ? (failed ? ' failed' : ' current') : '')
          const label = tr('state.' + s, s) + (failed && i === cur ? ` — ${t('state.failed')}` : '')
          return (
            <li key={s}>
              {canJump(s, i) ? (
                <button type="button" className={cls} onClick={() => jump(s)} title={t('ed.jump_hint')}>
                  {label}
                </button>
              ) : (
                <span className={cls} aria-current={i === cur ? 'step' : undefined}>{label}</span>
              )}
            </li>
          )
        })}
      </ol>
      <p className="small muted">{t('ed.stepper_hint')}</p>
    </nav>
  )
}

// ---------------------------------------------------------------- "what to do next"
function NextStep({ ep, hasShots, scriptDirty, isExplainer, setTab, onChanged, onRebuild, onEpisode, jobsActive }: {
  ep: Episode
  hasShots: boolean
  scriptDirty: boolean
  isExplainer: boolean
  setTab: (k: Tab) => void
  onChanged: () => void
  onRebuild: () => void
  onEpisode: (e: Episode) => void
  jobsActive: boolean
  }) {
  const { t, tr } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const post = <T,>(path: string, body: unknown = {}, success?: string) => act.run(() => api.post<T>(`/episodes/${ep.id}/${path}`, body), { success })
  const active = ep.jobs.filter(isActive)
  const s = ep.state
  const script = ep.script as Script
  const hasScript = (script.blocks ?? []).length > 0

  const genScript = async () => { if (await post('generate-script', {}, t('next.started'))) onChanged() }
  const approveScript = async () => {
    const r = await post<{ episode: Episode }>('approve-script', {}, t('next.script_approved'))
    if (r) { onEpisode(r.episode); setTab('storyboard') }
  }
  const genBoard = async () => { if (await post('generate-storyboard', {}, t('next.started'))) { onChanged(); setTab('storyboard') } }
  const approveBoard = async () => {
    const r = await post<Episode>('approve-storyboard', {}, t('next.board_approved'))
    if (r) { onEpisode(r); setTab('production') }
  }
  const produce = async (mode: 'preview' | 'final') => { if (await post('produce', { mode }, t('prod.started'))) { onChanged(); setTab('production') } }
  const approve = async () => {
    if (!(await confirm({ message: t('next.approve_confirm'), confirmLabel: t('next.approve') }))) return
    const r = await post<Episode>('approve', {}, t('next.approved'))
    if (r) onEpisode(r)
  }
  const revoke = async () => {
    if (!(await confirm({ message: t('next.revoke_confirm'), confirmLabel: t('next.revoke') }))) return
    const r = await post<Episode>('revoke', {}, t('next.revoked'))
    if (r) onEpisode(r)
  }
  const retry = async (mode: 'preview' | 'final') => { const r = await post<{ episode: Episode }>('retry', { mode }, t('next.retrying')); if (r) { onEpisode(r.episode) } }
  const reopen = async () => { const r = await act.run(async () => { await api.post(`/episodes/${ep.id}/transition`, { to: 'draft', reason: 'reopened' }); return true }); if (r) onRebuild() }
  const cancelEp = async () => {
    if (!(await confirm({ message: t('next.cancel_confirm'), danger: true, confirmLabel: t('next.cancel') }))) return
    const r = await act.run(async () => { await api.post(`/episodes/${ep.id}/transition`, { to: 'cancelled', reason: 'cancelled by owner' }); return true })
    if (r) onRebuild()
  }

  let body: ReactNode
  let tone: 'info' | 'warn' | 'ok' | 'err' = 'info'
  if (s === 'draft' || s === 'planned') {
    body = (
      <>
        <p>{t('next.planned')}</p>
        {isExplainer && <Notice tone="info"><span>{t('next.explainer_research')}</span> <Button size="sm" onClick={() => setTab('research')}>{t('ed.tab_research')}</Button></Notice>}
        <div className="row">
          <Button variant="primary" icon="spark" busy={act.busy} disabled={jobsActive} onClick={genScript}>{t('next.gen_script')}</Button>
          <Button onClick={() => setTab('script')}>{t('script.write_manual')}</Button>
        </div>
      </>
    )
  } else if (s === 'scripting') {
    body = <p>{t('next.scripting')}</p>
  } else if (s === 'script_review') {
    body = (
      <>
        <p>{t('next.script_review')}</p>
        {scriptDirty && <Notice tone="warn">{t('next.script_unsaved')}</Notice>}
        <div className="row">
          <Button variant="primary" icon="check" busy={act.busy} disabled={scriptDirty || !hasScript} onClick={approveScript}>{t('next.approve_script')}</Button>
          <Button onClick={() => setTab('script')}>{t('next.edit_script')}</Button>
        </div>
      </>
    )
  } else if (s === 'storyboarding') {
    body = hasShots ? (
      <>
        <p>{t('next.board_review')}</p>
        <div className="row">
          <Button variant="primary" icon="check" busy={act.busy} disabled={jobsActive} onClick={approveBoard}>{t('next.approve_board')}</Button>
          <Button icon="refresh" busy={act.busy} disabled={jobsActive} onClick={async () => { if (await confirm({ message: t('next.board_redo_confirm'), confirmLabel: t('next.redo_board') })) genBoard() }}>{t('next.redo_board')}</Button>
        </div>
      </>
    ) : (
      <>
        <p>{t('next.gen_board_text')}</p>
        <div className="row">
          <Button variant="primary" icon="spark" busy={act.busy} disabled={jobsActive} onClick={genBoard}>{t('next.gen_board')}</Button>
        </div>
      </>
    )
  } else if (s === 'asset_generation' || s === 'animation' || s === 'assembly') {
    body = active.some((j) => j.kind.startsWith('prod.')) ? <p>{t('next.producing')}</p> : (
      <>
        <p>{t('next.start_production')}</p>
        <div className="row">
          <Button variant="primary" icon="play" busy={act.busy} onClick={() => produce('preview')}>{t('prod.make_preview')}</Button>
          <Button icon="film" busy={act.busy} onClick={() => produce('final')}>{t('prod.make_final')}</Button>
        </div>
      </>
    )
  } else if (s === 'quality_review' || s === 'ready_for_approval') {
    tone = 'warn'
    const hasVideo = ep.videos.length > 0
    const latest = ep.videos[0]
    body = (
      <>
        <p>{t(s === 'quality_review' ? 'next.quality' : 'next.ready')}</p>
        {latest?.role === 'preview' && <Notice tone="info">{t('next.preview_only')}</Notice>}
        <div className="row">
          <Button variant="primary" icon="check" busy={act.busy} disabled={!hasVideo} onClick={approve}>{t('next.approve')}</Button>
          <Button icon="film" busy={act.busy} disabled={jobsActive} onClick={() => produce('final')}>{t('prod.make_final')}</Button>
          <Button icon="play" busy={act.busy} disabled={jobsActive} onClick={() => produce('preview')}>{t('prod.make_preview')}</Button>
        </div>
      </>
    )
  } else if (s === 'approved' || s === 'scheduled') {
    tone = 'ok'
    body = (
      <>
        <p>{t('next.approved_text')}</p>
        <div className="row">
          <LinkButton to={`/pages/${ep.page}/publishing`} variant="primary" icon="publish">{t('next.go_publish')}</LinkButton>
          {s === 'approved' && <Button busy={act.busy} onClick={revoke}>{t('next.revoke')}</Button>}
        </div>
      </>
    )
  } else if (s === 'published') {
    tone = 'ok'
    body = <p>{t('next.published')}</p>
  } else if (s === 'failed') {
    tone = 'err'
    body = (
      <>
        <p>{t('next.failed', { state: tr('state.' + ep.failed_state, ep.failed_state || '—') })}</p>
        {ep.error && <Notice tone="err"><ErrorText text={ep.error} /></Notice>}
        <div className="row">
          <Button variant="primary" icon="refresh" busy={act.busy} onClick={() => retry('preview')}>{t('next.retry_preview')}</Button>
          <Button icon="refresh" busy={act.busy} onClick={() => retry('final')}>{t('next.retry_final')}</Button>
        </div>
        <p className="small muted">{t('next.retry_note')}</p>
      </>
    )
  } else if (s === 'cancelled') {
    body = (
      <>
        <p>{t('next.cancelled')}</p>
        <div><Button busy={act.busy} onClick={reopen}>{t('next.reopen')}</Button></div>
      </>
    )
  }

  const canCancel = ep.allowed_next.some((a) => a.state === 'cancelled')
  return (
    <Card className="next-card" title={<span className="row"><Badge tone={tone}>{t('next.title')}</Badge></span>} actions={canCancel ? <Button size="sm" variant="ghost" onClick={cancelEp}>{t('next.cancel')}</Button> : undefined}>
      <div className="stack">
        {body}
        {active.length > 0 && (
          <div className="stack-sm">
            {active.slice(0, 3).map((j) => (
              <JobView key={j.id} job={j} compact />
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}

