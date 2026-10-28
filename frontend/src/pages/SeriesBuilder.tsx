import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Arc, EpisodeBrief, Memory, MemoryKind, PageDetail, SeriesDetail, SeriesPlan } from '../api/types'
import { useConfirm } from '../components/feedback'
import { JobView, StateBadge } from '../components/domain'
import { PlanEditor } from '../components/PlanEditor'
import { SourcesPanel } from '../components/SourcesPanel'
import { Async, AreaField, Badge, Button, Card, CardSkeletons, Empty, ErrorState, Link, LinkButton, Loading, Notice, NumberField, PageHead, SelectField, StringListField, SwitchField, Tabs, TextField } from '../components/ui'
import { ANIME, EXPLAINER } from '../formats'
import { useAction, useHashTab, useJobRunner, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

const TABS = ['info', 'arcs', 'episodes', 'plan', 'memory', 'sources'] as const
type Tab = (typeof TABS)[number]

export default function SeriesBuilder() {
  const { t } = useI18n()
  const { id } = useParams()
  const q = useQuery<SeriesDetail>(`/series/${id}`)
  const page = useQuery<PageDetail>(q.data ? `/pages/${q.data.page}` : null)
  const [tab, setTab] = useHashTab(TABS, 'info')
  useTitle(q.data?.title)
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Loading />
  const s = q.data
  const isAnime = s.format === ANIME
  const isExplainer = s.format === EXPLAINER
  const tabs = TABS.filter((k) => k !== 'sources' || isExplainer)
  const labels: Record<Tab, string> = { info: t('sb.tab_info'), arcs: t('sb.tab_arcs'), episodes: t('sb.tab_episodes'), plan: t('sb.tab_plan'), memory: t('sb.tab_memory'), sources: t('sb.tab_sources') }
  const crumbs = [{ label: t('nav.pages'), to: '/pages' }, { label: page.data?.name ?? '…', to: `/pages/${s.page}` }, { label: t('ws.tab_series'), to: `/pages/${s.page}/series` }, { label: s.title }]
  return (
    <div className="stack">
      <PageHead title={s.title} crumbs={crumbs}>
        <div className="row">
          <Badge tone="info">{t(('series.status.' + (['draft', 'planned', 'running', 'done'].includes(s.status) ? s.status : 'draft')) as 'series.status.draft')}</Badge>
          <Badge>{t('series.episodes_n', { n: s.episodes.length })}</Badge>
          {s.is_fan_content && <Badge tone="warn">{t('series.fan_badge')}</Badge>}
        </div>
      </PageHead>
      {s.notices.map((n) => (
        <Notice key={n.key} tone="warn">{n.text}</Notice>
      ))}
      <Tabs tabs={tabs.map((k) => ({ key: k, label: labels[k] }))} value={tabs.includes(tab) ? tab : 'info'} onChange={setTab} label={t('sb.tabs')} />
      {tab === 'info' && <InfoTab s={s} isAnime={isAnime} onSaved={(d) => q.setData(d)} />}
      {tab === 'arcs' && <ArcsTab s={s} reload={q.reload} />}
      {tab === 'episodes' && <EpisodesTab s={s} reload={q.reload} />}
      {tab === 'plan' && <PlanTab s={s} isAnime={isAnime} onApplied={(d) => { q.setData(d); setTab('episodes') }} />}
      {tab === 'memory' && <MemoryTab s={s} />}
      {tab === 'sources' && isExplainer && <SourcesPanel pageId={s.page} seriesId={s.id} />}
    </div>
  )
}

// ---------------------------------------------------------------- premise, branch, rules, fan switch
function InfoTab({ s, isAnime, onSaved }: { s: SeriesDetail; isAnime: boolean; onSaved: (d: SeriesDetail) => void }) {
  const { t } = useI18n()
  const nav = useNavigate()
  const confirm = useConfirm()
  const init = { title: s.title, premise: s.premise, branch_point: s.branch_point, alternative_timeline: s.alternative_timeline, content_rules: s.content_rules, is_fan_content: s.is_fan_content, franchise: s.franchise, target_episodes: s.target_episodes }
  const [d, setD] = useState(init)
  useEffect(() => setD(init), [s.title, s.premise, s.branch_point, s.alternative_timeline, s.is_fan_content, s.franchise, s.target_episodes, JSON.stringify(s.content_rules)]) // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(d) !== JSON.stringify(init)
  const act = useAction()
  const save = async () => {
    const r = await act.run(() => api.patch<SeriesDetail>(`/series/${s.id}`, d), { success: t('common.saved') })
    if (r) onSaved(r)
  }
  const remove = async () => {
    if (!(await confirm({ message: t('sb.delete_confirm', { title: s.title }), danger: true, confirmLabel: t('common.delete') }))) return
    const ok = await act.run(async () => {
      await api.del(`/series/${s.id}`)
      return true
    }, { success: t('sb.deleted') })
    if (ok) nav(`/pages/${s.page}/series`)
  }
  return (
    <div className="stack">
      <Card>
        <div className="stack">
          <TextField label={t('wiz.series_title')} required value={d.title} onChange={(v) => setD({ ...d, title: v })} />
          <AreaField label={t('wiz.series_premise')} value={d.premise} onChange={(v) => setD({ ...d, premise: v })} hint={t('sb.premise_hint')} />
          {isAnime && (
            <>
              <AreaField label={t('wiz.series_branch')} value={d.branch_point} onChange={(v) => setD({ ...d, branch_point: v })} hint={t('sb.branch_hint')} />
              <AreaField label={t('sb.alt_timeline')} value={d.alternative_timeline} onChange={(v) => setD({ ...d, alternative_timeline: v })} hint={t('sb.alt_hint')} />
            </>
          )}
          <NumberField label={t('sb.target_eps')} min={1} max={60} value={d.target_episodes} onChange={(v) => setD({ ...d, target_episodes: v ?? 1 })} />
          <StringListField label={t('pf.content_rules')} hint={t('sb.rules_hint')} value={d.content_rules} onChange={(v) => setD({ ...d, content_rules: v })} addLabel={t('pf.add_rule')} />
          {isAnime && (
            <fieldset className="card soft flat stack-sm" style={{ margin: 0 }}>
              <legend className="strong">{t('sb.fan_title')}</legend>
              <SwitchField label={t('wiz.fan')} hint={t('wiz.fan_hint')} checked={d.is_fan_content} onChange={(v) => setD({ ...d, is_fan_content: v })} />
              {d.is_fan_content && (
                <>
                  <Notice tone="warn">{t('sb.fan_notice')}</Notice>
                  <TextField label={t('wiz.franchise')} value={d.franchise} onChange={(v) => setD({ ...d, franchise: v })} />
                </>
              )}
            </fieldset>
          )}
        </div>
      </Card>
      <div className="sticky-actions">
        <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty || !d.title.trim()} onClick={save}>
          {t('common.save')}
        </Button>
        <Button disabled={!dirty} onClick={() => setD(init)}>{t('prof.revert')}</Button>
        <span className="spacer grow" />
        <Button variant="danger" icon="trash" onClick={remove}>{t('sb.delete')}</Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- arcs
function ArcsTab({ s, reload }: { s: SeriesDetail; reload: () => void }) {
  const { t } = useI18n()
  const act = useAction()
  const add = () => act.run(async () => { await api.post(`/series/${s.id}/arcs`, { title: t('sb.arc_n', { n: s.arcs.length + 1 }) }); reload() })
  return (
    <div className="stack">
      <div className="row between">
        <h2>{t('sb.tab_arcs')}</h2>
        <Button variant="primary" icon="plus" busy={act.busy} onClick={add}>{t('sb.add_arc')}</Button>
      </div>
      <p className="muted">{t('sb.arcs_intro')}</p>
      {s.arcs.length === 0 ? (
        <Empty icon="layers" title={t('sb.arcs_empty')} text={t('sb.arcs_empty_text')} />
      ) : (
        s.arcs.map((a) => <ArcCard key={a.id} a={a} reload={reload} />)
      )}
    </div>
  )
}

function ArcCard({ a, reload }: { a: Arc; reload: () => void }) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const [d, setD] = useState({ title: a.title, summary: a.summary, goal: a.goal, cliffhanger: a.cliffhanger })
  const dirty = d.title !== a.title || d.summary !== a.summary || d.goal !== a.goal || d.cliffhanger !== a.cliffhanger
  const act = useAction()
  return (
    <Card title={t('sb.arc_n', { n: a.index })}>
      <div className="stack">
        <TextField label={t('sb.arc_title')} value={d.title} onChange={(v) => setD({ ...d, title: v })} />
        <AreaField label={t('sb.arc_summary')} compact value={d.summary} onChange={(v) => setD({ ...d, summary: v })} />
        <div className="grid-2">
          <AreaField label={t('sb.goal')} compact value={d.goal} onChange={(v) => setD({ ...d, goal: v })} />
          <AreaField label={t('sb.cliffhanger')} compact value={d.cliffhanger} onChange={(v) => setD({ ...d, cliffhanger: v })} />
        </div>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty || !d.title.trim()} onClick={() => act.run(async () => { await api.patch(`/arcs/${a.id}`, d); reload() }, { success: t('common.saved') })}>
            {t('common.save')}
          </Button>
          <Button variant="ghost" icon="trash" onClick={async () => {
            if (await confirm({ message: t('sb.arc_delete_confirm'), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/arcs/${a.id}`); reload() }, { success: t('sb.arc_deleted') })
          }}>
            {t('common.delete')}
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- episode plan
function EpisodesTab({ s, reload }: { s: SeriesDetail; reload: () => void }) {
  const { t } = useI18n()
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [logline, setLogline] = useState('')
  const act = useAction()
  const add = async () => {
    const r = await act.run(async () => { await api.post(`/series/${s.id}/episodes`, { title: title.trim(), logline }); return true }, { success: t('sb.ep_added') })
    if (r) {
      setTitle('')
      setLogline('')
      setAdding(false)
      reload()
    }
  }
  return (
    <div className="stack">
      <div className="row between">
        <h2>{t('sb.tab_episodes')}</h2>
        <Button variant="primary" icon="plus" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>{t('sb.add_episode')}</Button>
      </div>
      <p className="muted">{t('sb.eps_intro')}</p>
      {adding && (
        <Card title={t('sb.add_episode')}>
          <div className="stack">
            <TextField label={t('sb.ep_title')} required value={title} onChange={setTitle} autoFocus />
            <AreaField label={t('sb.ep_logline')} compact value={logline} onChange={setLogline} />
            <div className="row">
              <Button variant="primary" icon="check" busy={act.busy} disabled={!title.trim()} onClick={add}>{t('common.add')}</Button>
              <Button onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
            </div>
          </div>
        </Card>
      )}
      {s.episodes.length === 0 ? (
        <Empty icon="film" title={t('sb.eps_empty')} text={t('sb.eps_empty_text')} />
      ) : (
        s.episodes.map((e) => <EpisodeCard key={e.id + ':' + e.updated_at} e={e} arcs={s.arcs} reload={reload} />)
      )}
    </div>
  )
}

function EpisodeCard({ e, arcs, reload }: { e: EpisodeBrief; arcs: Arc[]; reload: () => void }) {
  const { t, f } = useI18n()
  const confirm = useConfirm()
  const [d, setD] = useState({ title: e.title, logline: e.logline, goal: e.goal, cliffhanger: e.cliffhanger, duration_sec: e.duration_sec as number | null, arc: String(e.arc ?? '') })
  const dirty = d.title !== e.title || d.logline !== e.logline || d.goal !== e.goal || d.cliffhanger !== e.cliffhanger || d.duration_sec !== e.duration_sec || d.arc !== String(e.arc ?? '')
  const act = useAction()
  const started = !['draft', 'planned'].includes(e.state)
  return (
    <Card
      title={<span className="row">{t('episode.number', { n: e.number })}<StateBadge state={e.state} label={e.state_label} /></span>}
      actions={<LinkButton to={`/episodes/${e.id}`} size="sm" icon="film">{t('sb.open_editor')}</LinkButton>}
    >
      <div className="stack">
        <TextField label={t('sb.ep_title')} value={d.title} onChange={(v) => setD({ ...d, title: v })} />
        <AreaField label={t('sb.ep_logline')} compact value={d.logline} onChange={(v) => setD({ ...d, logline: v })} />
        <div className="grid-2">
          <AreaField label={t('sb.goal')} compact value={d.goal} onChange={(v) => setD({ ...d, goal: v })} />
          <AreaField label={t('sb.cliffhanger')} compact value={d.cliffhanger} onChange={(v) => setD({ ...d, cliffhanger: v })} />
        </div>
        <div className="grid-2">
          <SelectField label={t('sb.ep_arc')} value={d.arc} onChange={(v) => setD({ ...d, arc: v })} options={[{ value: '', label: '—' }, ...arcs.map((a) => ({ value: String(a.id), label: `${f.num(a.index)}. ${a.title}` }))]} />
          <NumberField label={t('sb.ep_duration')} min={10} max={180} value={d.duration_sec} onChange={(v) => setD({ ...d, duration_sec: v })} />
        </div>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty || !d.title.trim()} onClick={() => act.run(async () => { await api.patch(`/episodes/${e.id}`, { ...d, arc: d.arc ? Number(d.arc) : null, duration_sec: d.duration_sec ?? e.duration_sec }); reload() }, { success: t('common.saved') })}>
            {t('common.save')}
          </Button>
          <Button variant="ghost" icon="trash" onClick={async () => {
            if (await confirm({ message: started ? t('sb.ep_delete_started') : t('sb.ep_delete_confirm'), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/episodes/${e.id}`); reload() }, { success: t('sb.ep_deleted') })
          }}>
            {t('common.delete')}
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- AI plan proposal
function PlanTab({ s, isAnime, onApplied }: { s: SeriesDetail; isAnime: boolean; onApplied: (d: SeriesDetail) => void }) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const [count, setCount] = useState<number | null>(s.target_episodes)
  const [plan, setPlan] = useState<SeriesPlan | null>(null)
  const runner = useJobRunner<{ plan: SeriesPlan }>({
    onSucceeded: (j) => {
      const p = j.result.plan as SeriesPlan | undefined
      if (p) setPlan({ ...p, arcs: p.arcs ?? [], episodes: p.episodes ?? [] })
    },
  })
  const apply = useAction()
  const valid = !!plan && plan.title.trim() && plan.premise.trim() && plan.arcs.length > 0 && plan.arcs.every((a) => a.title.trim() && a.summary.trim()) && plan.episodes.length > 0 && plan.episodes.every((e) => e.title.trim() && e.logline.trim())
  const doApply = async () => {
    if (!plan) return
    if (!(await confirm({ message: t('sb.apply_confirm'), confirmLabel: t('sb.apply') }))) return
    const d = await apply.run(() => api.post<SeriesDetail>(`/series/${s.id}/apply-plan`, { plan }), { success: t('sb.applied') })
    if (d) onApplied(d)
  }
  return (
    <div className="stack">
      <div>
        <h2>{t('sb.tab_plan')}</h2>
        <p className="muted">{t('sb.plan_intro')}</p>
      </div>
      <Card>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <NumberField label={t('sb.plan_count')} min={1} max={60} value={count} onChange={setCount} className="grow" />
          <Button variant="primary" icon="spark" busy={runner.starting} disabled={runner.busy} onClick={() => runner.start(() => api.post(`/series/${s.id}/plan`, { episodes_count: count ?? s.target_episodes }))}>
            {t('sb.make_plan')}
          </Button>
        </div>
        {runner.job && !runner.succeeded && <div style={{ marginBlockStart: '0.75rem' }}><JobView job={runner.job} offline={runner.offline} /></div>}
      </Card>
      {plan && (
        <div className="split plan-split">
          <Card title={t('sb.current')} soft>
            <div className="stack-sm">
              <p className="strong">{s.title}</p>
              <p className="small muted">{s.premise || '—'}</p>
              <p className="small">{t('sb.current_counts', { a: s.arcs.length, e: s.episodes.length })}</p>
              <ol className="small" style={{ paddingInlineStart: '1.25rem', margin: 0 }}>
                {s.episodes.map((e) => (
                  <li key={e.id}>{e.title}</li>
                ))}
              </ol>
            </div>
          </Card>
          <Card title={t('sb.proposal')}>
            <div className="stack">
              <Notice tone="info">{t('sb.proposal_note')}</Notice>
              <PlanEditor value={plan} onChange={setPlan} withBranch={isAnime} />
              {!valid && <Notice tone="warn">{t('sb.plan_incomplete')}</Notice>}
              <div className="row">
                <Button variant="primary" icon="check" busy={apply.busy} disabled={!valid} onClick={doApply}>{t('sb.apply')}</Button>
                <Button onClick={() => { setPlan(null); runner.reset() }}>{t('strat.discard')}</Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- continuity (story memory)
const KINDS: MemoryKind[] = ['fact', 'character_state', 'relationship', 'timeline', 'open_thread', 'episode_summary', 'future_goal']

function MemoryTab({ s }: { s: SeriesDetail }) {
  const { t, f, tr } = useI18n()
  const confirm = useConfirm()
  const q = useQuery<Memory>(`/series/${s.id}/memory`)
  const [kind, setKind] = useState<MemoryKind>('fact')
  const [subject, setSubject] = useState('')
  const [text, setText] = useState('')
  const act = useAction()
  const add = async () => {
    const r = await act.run(() => api.post<Memory>(`/series/${s.id}/memory`, { kind, subject, text: text.trim() }), { success: t('mem.added') })
    if (r) {
      q.setData(r)
      setText('')
      setSubject('')
    }
  }
  const del = async (id: number) => {
    if (!(await confirm({ message: t('mem.delete_confirm'), danger: true, confirmLabel: t('common.delete') }))) return
    await act.run(async () => { await api.del(`/memory-entries/${id}`); q.reload() }, { success: t('mem.deleted') })
  }
  return (
    <div className="stack">
      <div>
        <h2>{t('sb.tab_memory')}</h2>
        <p className="muted">{t('mem.intro')}</p>
      </div>
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(m) => {
          const total = KINDS.reduce((n, k) => n + (m.entries[k]?.length ?? 0), 0)
          return (
            <>
              {total === 0 && <Empty icon="book" title={t('mem.empty_title')} text={t('mem.empty_text')} />}
              <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 340px), 1fr))' }}>
                {KINDS.map((k) => {
                  const rows = m.entries[k] ?? []
                  if (rows.length === 0) return null
                  return (
                    <Card key={k} title={<>{tr('mem.kind_' + k, k)} <span className="muted small">({f.num(rows.length)})</span></>}>
                      <div>
                        {rows.map((r) => (
                          <div key={r.id} className="mem-item">
                            <div className="grow">
                              {r.subject && <div className="strong small">{r.subject}</div>}
                              <div>{r.text}</div>
                              <div className="row small muted">
                                {r.episode != null && <span>{t('episode.number', { n: r.episode })}</span>}
                                {k === 'open_thread' && <Badge tone={r.status === 'resolved' ? 'ok' : 'warn'}>{r.status === 'resolved' ? t('mem.resolved') : t('mem.open')}</Badge>}
                              </div>
                            </div>
                            <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.delete')} onClick={() => del(r.id)} />
                          </div>
                        ))}
                      </div>
                    </Card>
                  )
                })}
              </div>
            </>
          )
        }}
      </Async>
      <Card title={t('mem.add')}>
        <div className="stack">
          <div className="grid-2">
            <SelectField label={t('mem.kind')} value={kind} onChange={(v) => setKind(v as MemoryKind)} options={KINDS.map((k) => ({ value: k, label: tr('mem.kind_' + k, k) }))} />
            <TextField label={t('mem.subject')} value={subject} onChange={setSubject} hint={t('mem.subject_hint')} />
          </div>
          <AreaField label={t('mem.text')} compact value={text} onChange={setText} />
          <div>
            <Button icon="plus" busy={act.busy} disabled={!text.trim()} onClick={add}>{t('common.add')}</Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
