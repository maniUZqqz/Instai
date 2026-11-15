import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { EpisodeBrief, PageBrief, Publication } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { JobView, StateBadge } from '../../components/domain'
import { DeliveryCard, NetworksCard } from '../../components/DeliveryCard'
import { Async, Badge, Button, Card, CardSkeletons, CheckField, Empty, ExtLink, Link, Loading, Notice, PageHead, SelectField, Tabs, TagsField, TextField, AreaField, type Tone } from '../../components/ui'
import { CoverStudio } from '../../covers/CoverStudio'
import { useAction, useJobRunner, useQuery, useTitle } from '../../hooks'
import { useI18n } from '../../i18n'
import { useWs } from './Workspace'

const ELIGIBLE = ['ready_for_approval', 'approved', 'scheduled', 'published']
const pubTone = (s: string): Tone => (s === 'published' ? 'ok' : s === 'scheduled' ? 'info' : s === 'exported' ? 'primary' : s === 'failed' ? 'err' : 'neutral')

function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export function PublishingTab() {
  const { page } = useWs()
  return <PublishingPanel pageId={page.id} />
}

function PublicationItems({ pageId, onMakeCover }: { pageId: number; onMakeCover: (episode: number) => void }) {
  const { t } = useI18n()
  const pubs = useQuery<Publication[]>(`/pages/${pageId}/publications`)
  const eps = useQuery<EpisodeBrief[]>(`/pages/${pageId}/episodes`)
  const [episode, setEpisode] = useState('')
  const [netTick, setNetTick] = useState(0)
  const act = useAction()
  const eligible = (eps.data ?? []).filter((e) => ELIGIBLE.includes(e.state))
  const add = async () => {
    const ep = eligible.find((e) => String(e.id) === episode)
    if (!ep) return
    const r = await act.run(() => api.post<Publication>(`/pages/${pageId}/publications`, { episode: ep.id, caption: ep.title }), { success: t('pub.created') })
    if (r) {
      setEpisode('')
      pubs.reload()
    }
  }
  return (
    <div className="stack">
      <Notice tone="info">{t('pub.manual_note')}</Notice>
      <Card title={t('dl.nets_title')}>
        <NetworksCard pageId={pageId} onChanged={() => setNetTick((n) => n + 1)} />
      </Card>
      <Card title={t('pub.new')}>
        {eps.loading && !eps.data ? (
          <Loading />
        ) : eligible.length === 0 ? (
          <p className="muted">{t('pub.no_eligible')}</p>
        ) : (
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <SelectField
              className="grow"
              label={t('pub.pick_episode')}
              value={episode}
              onChange={setEpisode}
              options={[{ value: '', label: t('pub.pick_ph') }, ...eligible.map((e) => ({ value: String(e.id), label: `${e.series_title ?? ''} · ${t('episode.number', { n: e.number })} · ${e.title}` }))]}
            />
            <Button variant="primary" icon="plus" disabled={!episode} busy={act.busy} onClick={add}>
              {t('pub.create')}
            </Button>
          </div>
        )}
      </Card>
      <Async q={pubs} skeleton={<CardSkeletons n={1} />}>
        {(list) =>
          list.length === 0 ? (
            <Empty icon="publish" title={t('pub.empty_title')} text={t('pub.empty_text')} />
          ) : (
            <div className="stack">
              {list.map((p) => (
                <PublicationCard key={p.id} p={p} onChanged={pubs.reload} netTick={netTick} onMakeCover={onMakeCover} />
              ))}
            </div>
          )
        }
      </Async>
    </div>
  )
}

function PublicationCard({ p, onChanged, netTick = 0, onMakeCover }: { p: Publication; onChanged: () => void; netTick?: number; onMakeCover: (episode: number) => void }) {
  const { t, f, tr } = useI18n()
  const confirm = useConfirm()
  const [caption, setCaption] = useState(p.caption)
  const [tags, setTags] = useState(p.hashtags)
  const [ai, setAi] = useState(p.ai_label)
  const [when, setWhen] = useState(toLocalInput(p.scheduled_at))
  const [ext, setExt] = useState(p.external_url)
  const act = useAction()
  const exporter = useJobRunner({ onFinished: () => onChanged() })
  useEffect(() => {
    setCaption(p.caption)
    setTags(p.hashtags)
    setAi(p.ai_label)
    setWhen(toLocalInput(p.scheduled_at))
    setExt(p.external_url)
  }, [p.id, p.caption, p.hashtags, p.ai_label, p.scheduled_at, p.external_url])
  const dirty = caption !== p.caption || JSON.stringify(tags) !== JSON.stringify(p.hashtags) || ai !== p.ai_label || when !== toLocalInput(p.scheduled_at)
  const eligible = ELIGIBLE.includes(p.episode_state)
  const save = () =>
    act.run(
      async () => {
        await api.patch(`/publications/${p.id}`, { caption, hashtags: tags, ai_label: ai, scheduled_at: when ? new Date(when).toISOString() : null })
        onChanged()
      },
      { success: t('common.saved') },
    )
  const remove = async () => {
    if (!(await confirm({ message: t('pub.delete_confirm'), danger: true, confirmLabel: t('common.delete') }))) return
    await act.run(async () => { await api.del(`/publications/${p.id}`); onChanged() }, { success: t('pub.deleted') })
  }
  const markPublished = async () => {
    if (!(await confirm({ message: t('pub.published_confirm'), confirmLabel: t('pub.mark_published') }))) return
    await act.run(async () => { await api.patch(`/publications/${p.id}`, { status: 'published', external_url: ext }); onChanged() }, { success: t('common.saved') })
  }
  return (
    <Card
      title={
        <span className="row">
          <Link to={`/episodes/${p.episode}`}>{p.episode_title || t('episode.number', { n: p.episode_number })}</Link>
          <span className="muted small">{t('episode.number', { n: p.episode_number })}</span>
        </span>
      }
      actions={
        <>
          <StateBadge state={p.episode_state} />
          <Badge tone={pubTone(p.status)}>{tr('pubstatus.' + p.status, p.status)}</Badge>
        </>
      }
    >
      <div className="stack">
        {!eligible && <Notice tone="warn">{t('pub.not_ready')}</Notice>}
        <div className="row">
          {p.cover_url ? <img className="cv-thumb" src={p.cover_url} alt={t('pub.cover')} loading="lazy" /> : <span className="small muted">{t('pub.cover_none')}</span>}
          <Button size="sm" icon="image" onClick={() => onMakeCover(p.episode)}>
            {t('pub.cover_make')}
          </Button>
        </div>
        <AreaField label={t('pub.caption')} value={caption} onChange={setCaption} />
        <TagsField label={t('strat.hashtags')} value={tags} onChange={setTags} ltr />
        <DeliveryCard pubId={p.id} caption={caption} tags={tags} savedAt={`${p.status}|${p.package_url ?? ''}|${netTick}`} />
        <CheckField label={t('pub.ai_label')} hint={t('pub.ai_label_hint')} checked={ai} onChange={setAi} />
        <div className="grid-2">
          <TextField label={t('pub.schedule')} type="datetime-local" ltr value={when} onChange={setWhen} hint={when ? f.dateTime(new Date(when)) : t('pub.schedule_hint')} />
          <TextField label={t('pub.external_url')} type="url" ltr value={ext} onChange={setExt} hint={t('pub.external_hint')} placeholder="https://" />
        </div>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>
            {t('common.save')}
          </Button>
          <Button icon="download" busy={exporter.starting} disabled={!eligible || exporter.busy || dirty} onClick={() => exporter.start(() => api.post(`/publications/${p.id}/export`, {}))}>
            {t('pub.export')}
          </Button>
          <Button onClick={markPublished} disabled={p.status === 'published' || !['scheduled', 'approved', 'published'].includes(p.episode_state)}>
            {t('pub.mark_published')}
          </Button>
          <Button variant="ghost" icon="trash" onClick={remove}>
            {t('common.delete')}
          </Button>
        </div>
        {dirty && <p className="small muted">{t('pub.save_first')}</p>}
        {exporter.job && !exporter.succeeded && <JobView job={exporter.job} offline={exporter.offline} />}
        {p.package_url && (
          <Notice tone="ok">
            <div className="row">
              <span>{t('pub.package_ready')}</span>
              <ExtLink href={p.package_url} download className="btn sm primary">
                {t('pub.download_package')}
              </ExtLink>
              {p.cover_url && <ExtLink href={p.cover_url}>{t('pub.cover')}</ExtLink>}
            </div>
          </Notice>
        )}
        {p.scheduled_at && <p className="small muted">{t('pub.scheduled_for', { when: f.dateTime(p.scheduled_at) })}</p>}
      </div>
    </Card>
  )
}

export function PublishingPanel({ pageId }: { pageId: number }) {
  const { t } = useI18n()
  const [tab, setTab] = useState<'items' | 'cover'>('items')
  const [episode, setEpisode] = useState(0)
  return (
    <div className="stack">
      <h2>{t('ws.tab_publishing')}</h2>
      <Tabs
        tabs={[
          { key: 'items', label: t('pub.tab_items') },
          { key: 'cover', label: t('pub.tab_cover') },
        ]}
        value={tab}
        onChange={setTab}
        label={t('ws.tab_publishing')}
      />
      {tab === 'items' ? (
        <PublicationItems
          pageId={pageId}
          onMakeCover={(ep) => {
            setEpisode(ep)
            setTab('cover')
          }}
        />
      ) : (
        <CoverTab pageId={pageId} episode={episode} setEpisode={setEpisode} />
      )}
    </div>
  )
}

/** The «Cover» tab: pick an episode and make its cover (the chosen one goes into the publishing package by itself). */
function CoverTab({ pageId, episode, setEpisode }: { pageId: number; episode: number; setEpisode: (id: number) => void }) {
  const { t } = useI18n()
  const eps = useQuery<EpisodeBrief[]>(`/pages/${pageId}/episodes`)
  const list = eps.data ?? []
  const cur = episode || list[0]?.id || 0
  if (eps.loading && !eps.data) return <Loading />
  if (list.length === 0) return <Empty icon="film" title={t('pub.tab_cover')} text={t('cv.no_episodes')} />
  return (
    <div className="stack">
      <SelectField
        label={t('pub.cover_pick')}
        value={String(cur)}
        onChange={(v) => setEpisode(Number(v))}
        options={list.map((e) => ({ value: String(e.id), label: `${e.series_title ?? ''} · ${t('cv.target_episode', { n: e.number, title: e.title })}` }))}
      />
      <CoverStudio key={cur} target={{ page: pageId, episode: cur, kind: 'episode' }} />
    </div>
  )
}

// ---------------------------------------------------------------- /publishing: every page's items in one list
interface Row extends Publication {
  pageId: number
  pageName: string
}

export default function PublishingCentre() {
  const { t, f, tr } = useI18n()
  useTitle(t('nav.publishing'))
  const pages = useQuery<PageBrief[]>('/pages')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!pages.data) return
    let alive = true
    Promise.all(pages.data.map((pg) => api.get<Publication[]>(`/pages/${pg.id}/publications`).then((l) => l.map((x) => ({ ...x, pageId: pg.id, pageName: pg.name })))))
      .then((all) => alive && setRows(all.flat().sort((a, b) => b.id - a.id)))
      .catch((e) => alive && setErr(e))
    return () => {
      alive = false
    }
  }, [pages.data, tick])
  return (
    <div className="stack">
      <PageHead title={t('nav.publishing')}>
        <Button icon="refresh" onClick={() => setTick((n) => n + 1)}>{t('common.refresh')}</Button>
      </PageHead>
      <Notice tone="info">{t('pub.manual_note')}</Notice>
      {err ? (
        <Notice tone="err">{t('error.generic')}</Notice>
      ) : !rows ? (
        <CardSkeletons n={1} />
      ) : rows.length === 0 ? (
        <Empty icon="publish" title={t('pub.empty_all_title')} text={t('pub.empty_all_text')} />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('pub.col_page')}</th>
                <th>{t('pub.col_episode')}</th>
                <th>{t('pub.col_status')}</th>
                <th>{t('pub.col_schedule')}</th>
                <th>{t('pub.col_package')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/pages/${r.pageId}/publishing`}>{r.pageName}</Link>
                  </td>
                  <td>
                    <Link to={`/episodes/${r.episode}`}>{r.episode_title}</Link> <span className="muted small">({t('episode.number', { n: r.episode_number })})</span>
                  </td>
                  <td>
                    <Badge tone={pubTone(r.status)}>{tr('pubstatus.' + r.status, r.status)}</Badge>
                  </td>
                  <td className="nowrap small">{r.scheduled_at ? f.dateTime(r.scheduled_at) : '—'}</td>
                  <td>{r.package_url ? <ExtLink href={r.package_url} download>{t('common.download')}</ExtLink> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
