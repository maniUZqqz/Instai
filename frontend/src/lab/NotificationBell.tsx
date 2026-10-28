import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Icon } from '../components/Icon'
import { Badge, Button } from '../components/ui'
import { useQuery } from '../hooks'
import type { NotificationRow, NotificationsPayload } from './api2'
import { useL } from './useL'
import './lab.css'

export function levelTone(l: NotificationRow['level']): 'ok' | 'warn' | 'err' | 'info' {
  return l === 'ok' ? 'ok' : l === 'warn' ? 'warn' : l === 'error' ? 'err' : 'info'
}

/** Header bell: unread count, a popover with the newest unread notices, mark as read. Polls every 10 s (and only while the tab is visible). */
export function NotificationBell() {
  const { s, f } = useL()
  const q = useQuery<NotificationsPayload>('/notifications?unread=1&limit=20', { interval: 10000 })
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const loc = useLocation()
  const nav = useNavigate()
  useEffect(() => setOpen(false), [loc.pathname])
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  const unread = q.data?.unread ?? 0
  const items = q.data?.items ?? []
  const markRead = async (ids: number[] | 'all') => {
    try {
      await api.post('/notifications/read', ids === 'all' ? { all: true } : { ids })
    } catch {
      /* the next poll shows the truth */
    }
    q.reload()
  }
  const label = unread ? s('nt.bell_unread', { n: unread }) : s('nt.bell_none')
  return (
    <div className="popover-wrap" ref={ref} data-testid="notification-bell">
      <button type="button" className="btn ghost sm" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((o) => !o)} aria-label={label} data-testid="bell-button">
        <Icon name="info" />
        <span className="nowrap" data-testid="bell-count">{unread ? f.num(unread) : ''}</span>
        <span className="sr-only" role="status">{label}</span>
      </button>
      {open && (
        <div className="popover stack-sm lab-bell-pop" data-testid="bell-popover">
          <div className="row between">
            <span className="strong">{label}</span>
            {unread > 0 && <Button size="sm" variant="ghost" onClick={() => markRead('all')} data-testid="bell-read-all">{s('nt.read_all')}</Button>}
          </div>
          {items.length === 0 && <p className="small muted">{s('nt.empty_short')}</p>}
          <ul className="lab-notes">
            {items.slice(0, 8).map((n) => (
              <li key={n.id} className="stack-sm" data-testid={`bell-item-${n.id}`}>
                <div className="row between nw">
                  <Badge tone={levelTone(n.level)}>{s(`nt.level_${n.level}` as 'nt.level_info')}</Badge>
                  <span className="small muted">{f.ago(n.created_at)}</span>
                </div>
                <div className="strong small">{n.title}</div>
                {n.body && <div className="small muted">{n.body}</div>}
                <div className="row">
                  {n.link && <Button size="sm" onClick={() => { markRead([n.id]); nav(n.link) }}>{s('nt.open')}</Button>}
                  <Button size="sm" variant="ghost" onClick={() => markRead([n.id])} data-testid={`bell-read-${n.id}`}>{s('nt.mark_read')}</Button>
                </div>
              </li>
            ))}
          </ul>
          <Button size="sm" variant="ghost" onClick={() => nav('/lab/notifications')}>{s('nt.see_all')}</Button>
        </div>
      )}
    </div>
  )
}
