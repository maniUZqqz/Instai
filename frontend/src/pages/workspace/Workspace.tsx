import { useOutletContext, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { EpisodeBrief, HistoryEvent, PageDetail, SeriesBrief } from '../../api/types'
import { StateBadge } from '../../components/domain'
import { Icon } from '../../components/Icon'
import { Async, Badge, Button, Card, CardSkeletons, Empty, ErrorState, Link, LinkButton, Loading, NavLink, Notice, PageHead, SelectField, TextField, AreaField, NumberField, Skeleton } from '../../components/ui'
import { useConfirm } from '../../components/feedback'
import { useAction, useQuery, useTitle } from '../../hooks'
import { ANIME, EXPLAINER, useFormats } from '../../formats'
import { useI18n } from '../../i18n'
import { Outlet } from 'react-router-dom'
import { useState } from 'react'

export interface WsCtx {
  page: PageDetail
  setPage: (p: PageDetail) => void
  reload: () => void
}
export const useWs = () => useOutletContext<WsCtx>()

const TABS = [
  { to: '', key: 'ws.tab_overview' },
  { to: 'settings', key: 'ws.tab_settings' },
  { to: 'characters', key: 'ws.tab_characters' },
  { to: 'series', key: 'ws.tab_series' },
  { to: 'episodes', key: 'ws.tab_episodes' },
  { to: 'publishing', key: 'ws.tab_publishing' },
  { to: 'history', key: 'ws.tab_history' },
] as const

export function Workspace() {
  const { t, tr } = useI18n()
  const { id } = useParams()
  const q = useQuery<PageDetail>(`/pages/${id}`)
  const { formatLabel } = useFormats()
  useTitle(q.data?.name)
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Loading />
  const page = q.data
  return (
    <div className="stack">
      <PageHead title={page.name} crumbs={[{ label: t('nav.pages'), to: '/pages' }, { label: page.name }]}>
        <div className="row">
          <Badge tone="primary">{formatLabel(page.format, page.format_label)}</Badge>
          <Badge>{tr('page.level.' + page.automation_level)}</Badge>
          {page.status === 'archived' && <Badge tone="warn">{t('page.archived')}</Badge>}
          {page.handle && <span className="muted ltr small">@{page.handle.replace(/^@/, '')}</span>}
        </div>
      </PageHead>
      <nav className="tabs" aria-label={t('ws.tabs')}>
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.to === ''} className={({ isActive }) => (isActive ? 'active' : '')}>
            {t(tab.key)}
          </NavLink>
        ))}
      </nav>
      <Outlet context={{ page, setPage: (p: PageDetail) => q.setData(p), reload: q.reload } satisfies WsCtx} />
    </div>
  )
}

// ---------------------------------------------------------------- overview
export function Overview() {
  const { t, f } = useI18n()
  const { page, setPage } = useWs()
  const nav = useNavigate()
  const confirm = useConfirm()
  const eps = useQuery<EpisodeBrief[]>(`/pages/${page.id}/episodes`, { interval: 8000 })
  const series = useQuery<SeriesBrief[]>(`/pages/${page.id}/series`)
  const act = useAction()
  const base = `/pages/${page.id}`

  const list = eps.data ?? []
  const count = (s: string) => list.filter((e) => e.state === s).length
  const actions: { tone: 'warn' | 'err' | 'info'; text: string; to: string; label: string }[] = []
  if (page.series_count === 0) actions.push({ tone: 'info', text: t('ov.no_series'), to: `${base}/series`, label: t('ov.create_series') })
  else if (page.episode_count === 0 && series.data?.[0]) actions.push({ tone: 'info', text: t('ov.no_episodes'), to: `/series/${series.data[0].id}#plan`, label: t('ov.make_plan') })
  if (page.profiles.strategy.positioning === '') actions.push({ tone: 'info', text: t('ov.no_strategy'), to: `${base}/settings`, label: t('ov.open_strategy') })
  if (page.format !== EXPLAINER && page.characters.length === 0) actions.push({ tone: 'info', text: t('ov.no_chars'), to: `${base}/characters`, label: t('ov.add_chars') })
  const first = (s: string) => list.find((e) => e.state === s)
  for (const [state, key] of [
    ['failed', 'ov.failed'],
    ['ready_for_approval', 'ov.ready'],
    ['script_review', 'ov.script_review'],
    ['quality_review', 'ov.quality'],
    ['storyboarding', 'ov.storyboard'],
    ['planned', 'ov.planned'],
  ] as const) {
    const n = count(state)
    const e = first(state)
    if (n && e) actions.push({ tone: state === 'failed' ? 'err' : state === 'ready_for_approval' ? 'warn' : 'info', text: t(key, { n }), to: `/episodes/${e.id}`, label: t('ov.open_episode') })
  }

  const toggleArchive = () =>
    act.run(
      async () => {
        const p = await api.patch<PageDetail>(`/pages/${page.id}`, { status: page.status === 'active' ? 'archived' : 'active' })
        setPage(p)
      },
      { success: t('common.saved') },
    )
  const remove = async () => {
    if (!(await confirm({ message: t('ov.delete_confirm', { name: page.name }), danger: true, confirmLabel: t('common.delete') }))) return
    const ok = await act.run(async () => {
      await api.del(`/pages/${page.id}`)
      return true
    }, { success: t('ov.deleted') })
    if (ok) nav('/pages')
  }

  return (
    <div className="stack-lg">
      <div className="grid-3">
        <Card>
          <div className="stat">
            <b>{f.num(page.series_count)}</b>
            <span className="muted">{t('page.stat_series')}</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <b>{f.num(page.episode_count)}</b>
            <span className="muted">{t('page.stat_episodes')}</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <b>{f.num(page.episodes_approved)}</b>
            <span className="muted">{t('page.stat_approved')}</span>
          </div>
        </Card>
      </div>

      {page.notices.length > 0 && (
        <div className="stack-sm">
          {page.notices.map((n) => (
            <Notice key={n.key} tone={n.key === 'fan' || n.key === 'presenter' ? 'warn' : 'info'}>
              {n.text}
            </Notice>
          ))}
        </div>
      )}

      <Card title={t('ov.next')}>
        {eps.loading && !eps.data ? (
          <Skeleton lines={3} />
        ) : actions.length === 0 ? (
          <p className="muted">{t('ov.nothing')}</p>
        ) : (
          <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {actions.map((a, i) => (
              <li key={i}>
                <Notice tone={a.tone}>
                  <div className="row between">
                    <span>{a.text}</span>
                    <Link to={a.to} className="strong">
                      {a.label}
                    </Link>
                  </div>
                </Notice>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {list.length > 0 && (
        <Card title={t('ov.by_state')}>
          <div className="row">
            {Array.from(new Set(list.map((e) => e.state))).map((s) => (
              <span key={s} className="row" style={{ gap: '0.35rem' }}>
                <StateBadge state={s} />
                <b>{f.num(count(s))}</b>
              </span>
            ))}
          </div>
        </Card>
      )}

      {page.idea && (
        <Card title={t('ov.idea')}>
          <p className="pre">{page.idea}</p>
        </Card>
      )}

      <Card title={t('ov.manage')}>
        <div className="row">
          <Button onClick={toggleArchive} busy={act.busy}>
            {page.status === 'active' ? t('ov.archive') : t('ov.unarchive')}
          </Button>
          <Button variant="danger" icon="trash" onClick={remove}>
            {t('ov.delete')}
          </Button>
        </div>
        <p className="small muted" style={{ marginBlockStart: '0.5rem' }}>
          {t('ov.delete_hint')}
        </p>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- series list
export function SeriesTab() {
  const { t, f } = useI18n()
  const { page, reload } = useWs()
  const nav = useNavigate()
  const q = useQuery<SeriesBrief[]>(`/pages/${page.id}/series`)
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [premise, setPremise] = useState('')
  const [branch, setBranch] = useState('')
  const [n, setN] = useState<number | null>(page.profiles.production.episodes_per_series ?? 5)
  const act = useAction()
  const create = async () => {
    const s = await act.run(() => api.post<{ id: number }>(`/pages/${page.id}/series`, { title: title.trim(), premise, branch_point: branch, target_episodes: n ?? 5 }), { success: t('series.created') })
    if (s) {
      reload()
      nav(`/series/${s.id}`)
    }
  }
  return (
    <div className="stack">
      <div className="row between">
        <h2>{t('ws.tab_series')}</h2>
        <Button variant="primary" icon="plus" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
          {t('series.new')}
        </Button>
      </div>
      {adding && (
        <Card title={t('series.new')}>
          <div className="stack">
            <TextField label={t('wiz.series_title')} required value={title} onChange={setTitle} autoFocus />
            <AreaField label={t('wiz.series_premise')} value={premise} onChange={setPremise} compact />
            {page.format === ANIME && <AreaField label={t('wiz.series_branch')} value={branch} onChange={setBranch} compact />}
            <NumberField label={t('wiz.series_episodes')} min={1} max={60} value={n} onChange={setN} />
            <div className="row">
              <Button variant="primary" icon="check" busy={act.busy} disabled={!title.trim()} onClick={create}>
                {t('series.create')}
              </Button>
              <Button onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
            </div>
          </div>
        </Card>
      )}
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(list) =>
          list.length === 0 ? (
            <Empty icon="layers" title={t('series.empty_title')} text={t('series.empty_text')} action={<Button variant="primary" icon="plus" onClick={() => setAdding(true)}>{t('series.new')}</Button>} />
          ) : (
            <div className="grid-auto">
              {list.map((s) => (
                <Link key={s.id} to={`/series/${s.id}`} className="card card-link stack-sm">
                  <h3>{s.title}</h3>
                  <p className="small muted" style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {s.premise || t('series.no_premise')}
                  </p>
                  <div className="row">
                    <Badge>{t('series.episodes_n', { n: f.num(s.episode_count) })}</Badge>
                    <Badge tone="info">{t('series.status.' + (['draft', 'planned', 'running', 'done'].includes(s.status) ? s.status : 'draft') as 'series.status.draft')}</Badge>
                    {s.is_fan_content && <Badge tone="warn">{t('series.fan_badge')}</Badge>}
                  </div>
                </Link>
              ))}
            </div>
          )
        }
      </Async>
    </div>
  )
}

// ---------------------------------------------------------------- episodes list
export function EpisodesTab() {
  const { t, f } = useI18n()
  const { page } = useWs()
  const q = useQuery<EpisodeBrief[]>(`/pages/${page.id}/episodes`, { interval: 6000 })
  const [filter, setFilter] = useState('')
  return (
    <div className="stack">
      <h2>{t('ws.tab_episodes')}</h2>
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(all) => {
          if (all.length === 0) return <Empty icon="film" title={t('eps.empty_title')} text={t('eps.empty_text')} action={<LinkButton to={`/pages/${page.id}/series`} variant="primary">{t('ws.tab_series')}</LinkButton>} />
          const states = Array.from(new Set(all.map((e) => e.state)))
          const list = all.filter((e) => !filter || e.state === filter)
          const groups = Array.from(new Set(list.map((e) => e.series)))
          return (
            <>
              <SelectField
                label={t('eps.filter')}
                value={filter}
                onChange={setFilter}
                options={[{ value: '', label: t('eps.filter_all') }, ...states.map((s) => ({ value: s, label: t(('state.' + s) as 'state.draft') }))]}
                className="grow"
              />
              {groups.map((sid) => {
                const rows = list.filter((e) => e.series === sid)
                return (
                  <Card key={sid} title={<Link to={`/series/${sid}`}>{rows[0].series_title}</Link>}>
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>{t('eps.col_no')}</th>
                            <th>{t('eps.col_title')}</th>
                            <th>{t('eps.col_state')}</th>
                            <th>{t('eps.col_len')}</th>
                            <th>{t('eps.col_updated')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((e) => (
                            <tr key={e.id}>
                              <td>{f.num(e.number)}</td>
                              <td>
                                <Link to={`/episodes/${e.id}`} className="strong">
                                  {e.title || t('episode.untitled', { n: e.number })}
                                </Link>
                                {e.logline && <div className="small muted">{e.logline}</div>}
                                {e.error && <div className="small" style={{ color: 'var(--err)' }}>{e.error.split('\n')[0].slice(0, 160)}</div>}
                              </td>
                              <td>
                                <StateBadge state={e.state} label={e.state_label} />
                              </td>
                              <td className="nowrap">{f.duration(e.duration_sec)}</td>
                              <td className="nowrap small muted">{f.ago(e.updated_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                )
              })}
            </>
          )
        }}
      </Async>
    </div>
  )
}

// ---------------------------------------------------------------- history
export function HistoryTab() {
  const { t, f, tr } = useI18n()
  const { page } = useWs()
  const q = useQuery<HistoryEvent[]>(`/pages/${page.id}/history`)
  return (
    <div className="stack">
      <h2>{t('ws.tab_history')}</h2>
      <p className="muted">{t('hist.intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={1} />}>
        {(list) =>
          list.length === 0 ? (
            <Empty icon="clock" title={t('hist.empty')} />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('hist.col_time')}</th>
                    <th>{t('hist.col_episode')}</th>
                    <th>{t('hist.col_change')}</th>
                    <th>{t('hist.col_reason')}</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((e) => (
                    <tr key={e.id}>
                      <td className="nowrap small">{f.dateTime(e.at)}</td>
                      <td>
                        <Link to={`/episodes/${e.episode}`}>
                          {e.series_title} · {t('episode.number', { n: e.episode_number })}
                        </Link>
                      </td>
                      <td>
                        {e.from && <span className="muted small">{tr('state.' + e.from, e.from)} ← </span>}
                        <StateBadge state={e.to} label={e.to_label} />
                      </td>
                      <td className="small">
                        {e.reason || '—'} <span className="muted">({tr('actor.' + e.actor, e.actor)})</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Async>
    </div>
  )
}
