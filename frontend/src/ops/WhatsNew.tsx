import { Async, Badge, Card, CardSkeletons, PageHead } from '../components/ui'
import { useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import type { ChangelogEntry } from './types'

/** "What is new": every version, newest first, in the language of the interface. Opened from the version badge. */
export default function WhatsNew() {
  const { t, lang, f } = useI18n()
  useTitle(t('ops.new.title'))
  const q = useQuery<{ name: string; current: string; entries: ChangelogEntry[] }>('/version/changelog')
  return (
    <div className="stack-lg">
      <PageHead title={t('ops.new.title')} />
      <p className="muted">{t('ops.new.intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(d) => (
          <div className="stack">
            {d.entries.map((e) => (
              <Card
                key={e.version}
                title={
                  <span className="row" style={{ gap: '0.6rem' }}>
                    <span className="ltr strong">v{e.version}</span>
                    {e.version === d.current && <Badge tone="primary">{t('ops.new.current')}</Badge>}
                    <span className="small muted">{f.date(e.date)}</span>
                  </span>
                }
              >
                <div className="stack-sm">
                  <div className="strong">{lang === 'en' ? e.title.en : e.title.fa}</div>
                  <ul className="stack-sm" style={{ margin: 0, paddingInlineStart: '1.25rem' }}>
                    {e.items.map((it, i) => (
                      <li key={i}>{lang === 'en' ? it.en : it.fa}</li>
                    ))}
                  </ul>
                </div>
              </Card>
            ))}
            {d.entries.length === 0 && <p className="muted">{t('ops.new.empty')}</p>}
          </div>
        )}
      </Async>
    </div>
  )
}
