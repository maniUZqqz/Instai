import { useState } from 'react'
import type { PageBrief } from '../api/types'
import { PageCard } from '../components/PageCard'
import { Async, CardSkeletons, Empty, LinkButton, PageHead, Segmented } from '../components/ui'
import { useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

export default function PagesList() {
  const { t } = useI18n()
  useTitle(t('nav.pages'))
  const q = useQuery<PageBrief[]>('/pages')
  const [filter, setFilter] = useState<'active' | 'all'>('active')
  return (
    <div className="stack">
      <PageHead title={t('nav.pages')}>
        <Segmented
          label={t('pages.filter')}
          value={filter}
          onChange={setFilter}
          options={[
            { key: 'active', label: t('pages.filter_active') },
            { key: 'all', label: t('pages.filter_all') },
          ]}
        />
        <LinkButton to="/pages/new" variant="primary" icon="plus">
          {t('dash.new_page')}
        </LinkButton>
      </PageHead>
      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(pages) => {
          const list = pages.filter((p) => filter === 'all' || p.status === 'active')
          return list.length === 0 ? (
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
              {list.map((p) => (
                <PageCard key={p.id} page={p} />
              ))}
            </div>
          )
        }}
      </Async>
    </div>
  )
}
