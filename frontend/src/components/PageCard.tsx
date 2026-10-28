import type { PageBrief } from '../api/types'
import { useFormats } from '../formats'
import { useI18n } from '../i18n'
import { Badge, Link } from './ui'

export function PageCard({ page }: { page: PageBrief }) {
  const { t, f, tr } = useI18n()
  const { formatLabel } = useFormats()
  return (
    <Link to={`/pages/${page.id}`} className="card card-link stack-sm">
      <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
        <h3 className="grow">{page.name}</h3>
        {page.status === 'archived' && <Badge>{t('page.archived')}</Badge>}
      </div>
      {page.handle && <div className="small muted ltr">@{page.handle.replace(/^@/, '')}</div>}
      <div className="row">
        <Badge tone="primary">{formatLabel(page.format, page.format_label)}</Badge>
        <Badge>{tr('page.level.' + page.automation_level)}</Badge>
      </div>
      <div className="row" style={{ gap: '1.25rem' }}>
        <span className="stat">
          <b>{f.num(page.series_count)}</b>
          <span className="small muted">{t('page.stat_series')}</span>
        </span>
        <span className="stat">
          <b>{f.num(page.episode_count)}</b>
          <span className="small muted">{t('page.stat_episodes')}</span>
        </span>
        <span className="stat">
          <b>{f.num(page.episodes_approved)}</b>
          <span className="small muted">{t('page.stat_approved')}</span>
        </span>
      </div>
    </Link>
  )
}
