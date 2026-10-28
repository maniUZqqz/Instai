import { Badge, Card, Link, PageHead } from '../components/ui'
import { Icon } from '../components/Icon'
import { useTitle } from '../hooks'
import { LAB_SCREENS } from './registry'
import type { LabKey } from './i18n'
import { useL } from './useL'
import './lab.css'

export default function Hub() {
  const { s } = useL()
  useTitle(s('lab.title'))
  return (
    <div className="stack-lg">
      <PageHead title={s('lab.title')} />
      <p className="muted">{s('lab.intro')}</p>
      <ul className="grid-auto lab-tiles" aria-label={s('lab.title')}>
        {LAB_SCREENS.map((sc) => {
          const enabled = !!sc.Component
          const title = s(`title.${sc.key}` as LabKey)
          const body = (
            <>
              <span className="lab-tile-icon" aria-hidden="true"><Icon name={sc.icon} size={26} /></span>
              <span className="strong">{title}</span>
              <span className="small muted">{s(`desc.${sc.key}` as LabKey)}</span>
              {!enabled && <Badge tone="neutral">{s('lab.soon')}</Badge>}
            </>
          )
          return (
            <li key={sc.key}>
              {enabled ? (
                <Link to={`/lab/${sc.path}`} className="card lab-tile" data-testid={`tile-${sc.key}`}>{body}</Link>
              ) : (
                <div className="card lab-tile disabled" aria-disabled="true" data-testid={`tile-${sc.key}`}>{body}</div>
              )}
            </li>
          )
        })}
      </ul>
      <Card soft>
        <p className="small muted">{s('lab.note')}</p>
      </Card>
    </div>
  )
}
