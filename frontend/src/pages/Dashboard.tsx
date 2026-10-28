import type { Dashboard as DashboardData } from '../api/types'
import { GpuMeter, JobView, StateBadge } from '../components/domain'
import { PageCard } from '../components/PageCard'
import { useApp } from '../components/Shell'
import { Async, Badge, Card, CardSkeletons, Empty, Link, LinkButton, Notice, PageHead } from '../components/ui'
import { useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

export default function Dashboard() {
  const { t, f, tr } = useI18n()
  useTitle(t('nav.dashboard'))
  const q = useQuery<DashboardData>('/dashboard', { interval: 5000 })
  const { demo } = useApp()
  return (
    <div className="stack-lg">
      <PageHead title={t('nav.dashboard')}>
        <LinkButton to="/pages/new" variant="primary" icon="plus">
          {t('dash.new_page')}
        </LinkButton>
      </PageHead>
      <Async q={q} skeleton={<CardSkeletons n={4} />}>
        {(d) => (
          <>
            {(d.demo_mode || demo) && (
              <Notice tone="warn">
                <strong>{t('dash.demo_title')}</strong> {t('dash.demo_text')}
              </Notice>
            )}

            <div className="grid-3">
              <Card title={t('dash.worker')}>
                {d.worker_alive ? (
                  <div className="row nw">
                    <span className="dot ok" aria-hidden="true" />
                    <span>{t('dash.worker_ok')}</span>
                  </div>
                ) : (
                  <Notice tone="err">{t('dash.worker_down')}</Notice>
                )}
              </Card>
              <Card title={t('dash.gpu')}>
                <GpuMeter gpu={d.gpu} busyReason={d.gpu.busy_reason} />
              </Card>
              <Card title={t('dash.provider')}>
                <div className="stack-sm">
                  <Badge tone={d.provider === 'fake' ? 'warn' : 'info'}>{tr('provider.' + d.provider, d.provider)}</Badge>
                  <Link to="/settings" className="small">
                    {t('dash.provider_change')}
                  </Link>
                </div>
              </Card>
            </div>

            {d.needs_action.length > 0 && (
              <Card title={t('dash.needs_action')}>
                <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                  {d.needs_action.map((n, i) => (
                    <li key={i} className="row">
                      <Badge tone={n.type === 'ready_for_approval' ? 'warn' : 'err'}>{t(('dash.action_' + n.type) as 'dash.action_job_failed')}</Badge>
                      <Link to={n.episode ? `/episodes/${n.episode}` : '/monitor'} className="strong">
                        {n.title}
                      </Link>
                      {n.error && <span className="small muted">{n.error}</span>}
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            <Card title={t('dash.active_jobs')} actions={<Link to="/monitor">{t('dash.open_monitor')}</Link>}>
              {d.active_jobs.length === 0 ? (
                <p className="muted">{t('dash.no_jobs')}</p>
              ) : (
                <div className="stack-sm">
                  {d.active_jobs.map((j) => (
                    <JobView key={j.id} job={j} compact />
                  ))}
                </div>
              )}
            </Card>

            <section className="stack" aria-labelledby="pages-h">
              <div className="row between">
                <h2 id="pages-h">{t('dash.pages')}</h2>
                <Link to="/pages">{t('dash.all_pages')}</Link>
              </div>
              {d.pages.length === 0 ? (
                <Empty
                  icon="pages"
                  title={t('pages.empty_title')}
                  text={t('pages.empty_text')}
                  action={
                    <LinkButton to="/pages/new" variant="primary" icon="plus">
                      {t('dash.new_page')}
                    </LinkButton>
                  }
                />
              ) : (
                <div className="grid-auto">
                  {d.pages.map((p) => (
                    <PageCard key={p.id} page={p} />
                  ))}
                </div>
              )}
            </section>

            <div className="split">
              <Card title={t('dash.recent_episodes')}>
                {d.recent_episodes.length === 0 ? (
                  <p className="muted">{t('dash.no_episodes')}</p>
                ) : (
                  <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {d.recent_episodes.map((e) => (
                      <li key={e.id}>
                        <Link to={`/episodes/${e.id}`} className="row between" style={{ flexWrap: 'nowrap', color: 'inherit', textDecoration: 'none' }}>
                          <span className="grow">
                            <span className="strong">{e.title || t('episode.untitled', { n: e.number })}</span>
                            <br />
                            <span className="small muted">
                              {e.page_name} · {e.series_title} · {t('episode.number', { n: e.number })} · {f.ago(e.updated_at)}
                            </span>
                          </span>
                          <StateBadge state={e.state} label={e.state_label} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title={t('dash.upcoming')} actions={<Link to="/publishing">{t('nav.publishing')}</Link>}>
                {d.upcoming_publications.length === 0 ? (
                  <p className="muted">{t('dash.no_upcoming')}</p>
                ) : (
                  <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {d.upcoming_publications.map((p) => (
                      <li key={p.id} className="row between">
                        <Link to={`/episodes/${p.episode}`}>{p.episode_title}</Link>
                        <span className="small muted">{f.dateTime(p.scheduled_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="small muted" style={{ marginBlockStart: '0.75rem' }}>
                  {t('pub.manual_note_short')}
                </p>
              </Card>
            </div>
          </>
        )}
      </Async>
    </div>
  )
}
