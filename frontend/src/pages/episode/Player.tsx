import type { ReactNode } from 'react'
import type { Episode, VideoAsset } from '../../api/types'
import { Badge } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { useI18n } from '../../i18n'

/** The states in which a finished video is what the owner came for: it is shown at the TOP of the episode page, next to the buttons that decide about it. */
export const PLAYER_STATES = ['quality_review', 'ready_for_approval', 'approved', 'scheduled', 'published']
export const REVIEW_STATES = ['quality_review', 'ready_for_approval']

/** The video the top of the page shows (the newest), or null when this state / this episode has none. */
export function topVideo(ep: Episode): VideoAsset | null {
  return PLAYER_STATES.includes(ep.state) && ep.videos.length > 0 ? ep.videos[0] : null
}

/** One <video>. A tall (9:16) video is limited to a phone-like width, a wide one takes the room it is given; it never stretches into black bars. */
export function VideoPlayer({ ep, v, label }: { ep: Episode; v: VideoAsset; label: string }) {
  const known = !!(v.width && v.height)
  const portrait = !known || (v.height as number) > (v.width as number)
  return (
    <div className={'ep-player ' + (portrait ? 'portrait' : 'landscape')} data-testid="ep-player">
      <video controls preload="metadata" src={v.url} poster={ep.cover_url ?? undefined} style={known ? { aspectRatio: `${v.width} / ${v.height}` } : undefined} aria-label={label}>
        <track kind="captions" />
      </video>
    </div>
  )
}

/** What the quality check found, in three lines: the verdict and the checks that are not plain «ok». The full list stays on the production tab. */
export function QcSummary({ ep, more }: { ep: Episode; more?: ReactNode }) {
  const { t, tr } = useI18n()
  const checks = ep.qc?.checks ?? []
  if (checks.length === 0) return null
  const open = checks.filter((c) => c.level !== 'ok')
  const icon = { ok: 'check', warn: 'alert', fail: 'close', info: 'info' } as const
  return (
    <div className="qc-summary stack-sm" data-testid="qc-summary">
      <div className="row">
        <strong>{t('prod.qc_title')}</strong>
        <Badge tone={ep.qc.ok ? 'ok' : 'err'}>{ep.qc.ok ? t('prod.qc_ok') : t('prod.qc_fail')}</Badge>
        <span className="small muted">{t('next.qc_count', { ok: checks.length - open.length, total: checks.length })}</span>
      </div>
      {open.length > 0 && (
        <ul className="qc-list small">
          {open.slice(0, 3).map((c, i) => (
            <li key={i}>
              <Icon name={icon[c.level]} />
              <span className="sr-only">{tr('qc.level_' + c.level, c.level)}</span>
              <span>{c.message}</span>
            </li>
          ))}
        </ul>
      )}
      {open.length > 3 && <span className="small muted">{t('next.qc_more', { n: open.length - 3 })}</span>}
      {more}
    </div>
  )
}
