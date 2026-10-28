import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Async, Badge, Button, Card, CardSkeletons, Empty, PageHead, Segmented } from '../components/ui'
import { useAction, useQuery, useTitle } from '../hooks'
import type { NotificationsPayload } from './api2'
import { levelTone } from './NotificationBell'
import { useL } from './useL'
import './lab.css'

export default function Notifications() {
  const { s, f } = useL()
  useTitle(s('title.notifications'))
  const [filter, setFilter] = useState<'unread' | 'all'>('unread')
  const q = useQuery<NotificationsPayload>(`/notifications?limit=100${filter === 'unread' ? '&unread=1' : ''}`, { interval: 10000 })
  const act = useAction()
  const nav = useNavigate()
  const mark = (body: object) => act.run(async () => { await api.post('/notifications/read', body); q.reload() })
  return (
    <div className="stack-lg">
      <PageHead title={s('title.notifications')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('title.notifications') }]}>
        <Button icon="check" busy={act.busy} onClick={() => mark({ all: true })} data-testid="notes-read-all">{s('nt.read_all')}</Button>
      </PageHead>
      <p className="muted">{s('nt.intro')}</p>
      <Segmented label={s('nt.filter')} value={filter} onChange={setFilter} options={[{ key: 'unread', label: s('nt.filter_unread') }, { key: 'all', label: s('nt.filter_all') }]} />
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(d) =>
          d.items.length === 0 ? (
            <Empty icon="info" title={s('nt.empty')} text={s('nt.empty_text')} />
          ) : (
            <ul className="stack-sm lab-notes" data-testid="notes-list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {d.items.map((n) => (
                <li key={n.id} data-testid={`note-${n.id}`}>
                  <Card>
                    <div className="stack-sm">
                      <div className="row between">
                        <span className="row">
                          <Badge tone={levelTone(n.level)}>{s(`nt.level_${n.level}` as 'nt.level_info')}</Badge>
                          <Badge tone="neutral">{n.kind}</Badge>
                          {!n.read && <Badge tone="primary">{s('nt.unread')}</Badge>}
                        </span>
                        <span className="small muted">{f.dateTime(n.created_at)}</span>
                      </div>
                      <div className="strong">{n.title}</div>
                      {n.body && <div className="small muted">{n.body}</div>}
                      <div className="row">
                        {n.link && <Button size="sm" icon="external" onClick={() => { if (!n.read) mark({ ids: [n.id] }); nav(n.link) }}>{s('nt.open')}</Button>}
                        {!n.read && <Button size="sm" variant="ghost" onClick={() => mark({ ids: [n.id] })} data-testid={`note-read-${n.id}`}>{s('nt.mark_read')}</Button>}
                      </div>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </Async>
    </div>
  )
}
