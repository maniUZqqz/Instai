import { Badge, Card, Link, PageHead } from '../components/ui'
import { Icon } from '../components/Icon'
import { useTitle } from '../hooks'
import { STUDIO_SCREENS } from './registry'
import type { StudioKey } from './i18n'
import { useS } from './useS'
import './studio.css'

export default function Hub() {
  const { s } = useS()
  useTitle(s('studio.title'))
  return (
    <div className="stack-lg">
      <PageHead title={s('studio.title')} />
      <p className="muted">{s('studio.intro')}</p>
      <ul className="grid-auto studio-tiles" aria-label={s('studio.title')}>
        {STUDIO_SCREENS.map((sc) => {
          const enabled = !!sc.Component
          const title = s(`title.${sc.key}` as StudioKey)
          const body = (
            <>
              <span className="studio-tile-icon" aria-hidden="true"><Icon name={sc.icon} size={26} /></span>
              <span className="strong">{title}</span>
              <span className="small muted">{s(`desc.${sc.key}` as StudioKey)}</span>
              {!enabled && <Badge tone="neutral">{s('studio.soon')}</Badge>}
            </>
          )
          return (
            <li key={sc.key}>
              {enabled ? (
                <Link to={`/studio/${sc.path}`} className="card studio-tile" data-testid={`tile-${sc.key}`}>{body}</Link>
              ) : (
                <div className="card studio-tile disabled" aria-disabled="true" data-testid={`tile-${sc.key}`}>{body}</div>
              )}
            </li>
          )
        })}
      </ul>
      <Card soft>
        <p className="small muted">{s('studio.note')}</p>
      </Card>
    </div>
  )
}
