import { Link } from '../components/ui'
import { Icon } from '../components/Icon'
import { useQuery } from '../hooks'
import { useI18n } from '../i18n'
import type { QueueSummary } from './types'

/** In the top bar of every screen: how many jobs WAIT (for a computer, Ollama, ComfyUI or the graphics card) and how many are scheduled.
 *  Nothing is shown while nothing waits. A click opens the processing queue. */
export function QueueBadge() {
  const { t, f } = useI18n()
  const q = useQuery<QueueSummary>('/queue/summary', { interval: 6000 })
  const s = q.data
  if (!s || (s.waiting <= 0 && s.scheduled <= 0)) return null
  const waiting = s.waiting > 0
  const label = waiting ? t('ops.badge.waiting', { n: s.waiting }) : t('ops.badge.scheduled', { n: s.scheduled })
  return (
    <Link to="/queue" className={'btn ghost sm queue-badge ' + (waiting ? 'warn' : '')} title={t('ops.badge.tip')} aria-label={label} data-testid="queue-badge">
      <Icon name="clock" />
      <span className="nowrap">{f.num(waiting ? s.waiting : s.scheduled)}</span>
      <span className="queue-badge-text">{waiting ? t('ops.badge.word_waiting') : t('ops.badge.word_scheduled')}</span>
    </Link>
  )
}
