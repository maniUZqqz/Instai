import { useState } from 'react'
import { api } from '../../api/client'
import type { Episode, EpisodeEvent, EpisodeVersion, ResearchClaim } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { JobView, StateBadge } from '../../components/domain'
import { SourcesPanel } from '../../components/SourcesPanel'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Notice, TextField } from '../../components/ui'
import { useAction, useJobRunner, useQuery } from '../../hooks'
import { useI18n } from '../../i18n'

const STANCES = ['established', 'contested', 'speculative'] as const

export function Research({ ep, onChanged }: { ep: Episode; onChanged: () => void }) {
  const { t, f, tr } = useI18n()
  const [topic, setTopic] = useState(ep.research?.topic || ep.title)
  const runner = useJobRunner({ onFinished: () => onChanged() })
  const claims: ResearchClaim[] = ep.research?.claims ?? []
  const byId = new Map(ep.sources.map((s) => [s.id, s]))
  const active = ep.jobs.find((j) => j.kind === 'story.research' && (j.status === 'queued' || j.status === 'running'))
  const running = runner.busy || !!active
  return (
    <div className="stack">
      <Notice tone="info">{t('res.intro')}</Notice>
      <Card title={t('res.run_title')}>
        <div className="stack">
          <TextField label={t('res.topic')} value={topic} onChange={setTopic} hint={t('res.topic_hint')} />
          <div>
            <Button variant="primary" icon="spark" busy={runner.starting} disabled={running || !topic.trim()} onClick={() => runner.start(() => api.post(`/episodes/${ep.id}/research`, { topic: topic.trim() }))}>
              {claims.length ? t('res.run_again') : t('res.run')}
            </Button>
          </div>
          {runner.job && !runner.succeeded && <JobView job={runner.job} offline={runner.offline} />}
          {!runner.job && active && <JobView job={active} />}
        </div>
      </Card>

      {claims.length === 0 ? (
        <Empty icon="book" title={t('res.empty_title')} text={t('res.empty_text')} />
      ) : (
        <Card title={t('res.claims')} actions={ep.research.at ? <span className="small muted">{f.dateTime(ep.research.at)}</span> : undefined}>
          <div className="stack">
            {(ep.research.unsupported_count ?? 0) > 0 && <Notice tone="warn">{t('res.unsupported_warn', { n: ep.research.unsupported_count ?? 0 })}</Notice>}
            {STANCES.map((st) => {
              const list = claims.filter((c) => c.stance === st)
              if (list.length === 0) return null
              return (
                <section key={st} className="stack-sm" aria-label={tr('stance.' + st)}>
                  <h3>
                    {tr('stance.' + st)} <span className="muted small">({list.length})</span>
                  </h3>
                  <p className="small muted">{t(('res.stance_' + st) as 'res.stance_established')}</p>
                  {list.map((c, i) => (
                    <div key={i} className={'claim ' + (c.unsupported ? 'unsupported' : st)}>
                      <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                        <span>{c.claim}</span>
                        {c.unsupported && <Badge tone="err">{t('res.unsupported')}</Badge>}
                      </div>
                      {c.explanation && <div className="small muted">{c.explanation}</div>}
                      {c.source_ids.length > 0 && (
                        <div className="chips" style={{ marginBlockStart: '0.35rem' }}>
                          {c.source_ids.map((id) => (
                            <span key={id} className="badge info">{byId.get(id)?.title ?? `#${id}`}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </section>
              )
            })}
            {([['analogies', 'res.analogies'], ['visual_metaphors', 'res.metaphors'], ['caveats', 'res.caveats']] as const).map(([k, label]) => {
              const items = (ep.research[k] as string[] | undefined) ?? []
              return items.length ? (
                <section key={k} className="stack-sm">
                  <h3>{t(label)}</h3>
                  <ul style={{ margin: 0, paddingInlineStart: '1.25rem' }}>
                    {items.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </section>
              ) : null
            })}
          </div>
        </Card>
      )}

      <Card title={t('res.sources')}>
        <div className="stack">
          {ep.sources.length > 0 && (
            <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {ep.sources.map((s) => (
                <li key={s.id} className="row">
                  {s.verified ? <Badge tone="ok">{t('src.verified')}</Badge> : <Badge tone="warn">{t('src.unverified')}</Badge>}
                  <span className="strong">{s.title}</span>
                  {s.url && <a href={s.url} target="_blank" rel="noreferrer noopener" className="ltr small">{s.url}</a>}
                  <Badge tone="info">{s.added_by === 'user' ? t('src.by_you') : t('src.by_system')}</Badge>
                </li>
              ))}
            </ul>
          )}
          <SourcesPanel pageId={ep.page} seriesId={ep.series} episodeId={ep.id} onChanged={onChanged} />
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- versions
export function Versions({ ep, onRestored }: { ep: Episode; onRestored: (e: Episode) => void }) {
  const { t, f } = useI18n()
  const confirm = useConfirm()
  const q = useQuery<EpisodeVersion[]>(`/episodes/${ep.id}/versions`)
  const act = useAction()
  const restore = async (v: EpisodeVersion) => {
    if (!(await confirm({ message: t(v.kind === 'script' ? 'ver.restore_script' : 'ver.restore_board'), confirmLabel: t('ver.restore') }))) return
    const e = await act.run(() => api.post<Episode>(`/episodes/${ep.id}/restore-version`, { version: v.id }), { success: t('ver.restored') })
    if (e) {
      onRestored(e)
      q.reload()
    }
  }
  return (
    <div className="stack">
      <p className="muted">{t('ver.intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={1} />}>
        {(list) =>
          list.length === 0 ? (
            <Empty icon="clock" title={t('ver.empty')} />
          ) : (
            <div className="stack-sm">
              {list.map((v) => {
                const blocks = v.kind === 'script' ? (v.data?.blocks?.length ?? 0) : 0
                const scenes = v.kind === 'storyboard' ? (v.data?.scenes?.length ?? 0) : 0
                const shots = v.kind === 'storyboard' ? (v.data?.scenes ?? []).reduce((n: number, s: { shots?: unknown[] }) => n + (s.shots?.length ?? 0), 0) : 0
                return (
                  <div key={v.id} className="card flat stack-sm">
                    <div className="row between">
                      <span className="row">
                        <Badge tone="primary">{t(v.kind === 'script' ? 'ver.script' : 'ver.board')}</Badge>
                        <span className="small muted">{f.dateTime(v.created_at)}</span>
                      </span>
                      <Button size="sm" busy={act.busy} onClick={() => restore(v)}>{t('ver.restore')}</Button>
                    </div>
                    <div className="small">
                      {v.kind === 'script' ? t('ver.script_info', { n: blocks }) : t('ver.board_info', { s: scenes, n: shots })}
                      {v.note ? ` · ${v.note}` : ''}
                    </div>
                    {v.kind === 'script' && v.data?.blocks?.[0]?.text && <div className="small muted">«{String(v.data.blocks[0].text).slice(0, 140)}…»</div>}
                  </div>
                )
              })}
            </div>
          )
        }
      </Async>
    </div>
  )
}

// ---------------------------------------------------------------- events
export function Events({ ep }: { ep: Episode }) {
  const { t, f, tr } = useI18n()
  const q = useQuery<EpisodeEvent[]>(`/episodes/${ep.id}/events`, { interval: 6000 })
  return (
    <Async q={q} skeleton={<CardSkeletons n={1} />}>
      {(list) => (
        <ol className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {[...list].reverse().map((e) => (
            <li key={e.id} className="card flat row between">
              <span className="row">
                <StateBadge state={e.to} label={e.to_label} />
                {e.reason && <span className="small">{e.reason}</span>}
              </span>
              <span className="small muted">
                {tr('actor.' + e.actor, e.actor)} · {f.dateTime(e.at)}
              </span>
            </li>
          ))}
          {list.length === 0 && <li className="muted">{t('hist.empty')}</li>}
        </ol>
      )}
    </Async>
  )
}
