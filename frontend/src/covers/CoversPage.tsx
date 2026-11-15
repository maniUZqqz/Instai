import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { EpisodeBrief, PageBrief, SeriesBrief } from '../api/types'
import { Empty, Loading, Notice, PageHead, Segmented, SelectField } from '../components/ui'
import { useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { CoverStudio } from './CoverStudio'
import type { CoverTarget } from './types'

type What = 'episode' | 'series' | 'banner'

/** /covers: pick a page, then an episode (or a series, or the channel banner), then the cover editor. `?page=&episode=` links straight to an episode. */
export default function CoversPage() {
  const { t } = useI18n()
  useTitle(t('cv.title'))
  const [params, setParams] = useSearchParams()
  const pages = useQuery<PageBrief[]>('/pages')
  const pageId = Number(params.get('page')) || pages.data?.[0]?.id || 0
  const what = (params.get('what') as What | null) ?? (params.get('series') ? 'series' : 'episode')
  const episodeId = Number(params.get('episode')) || 0
  const seriesId = Number(params.get('series')) || 0
  const eps = useQuery<EpisodeBrief[]>(pageId ? `/pages/${pageId}/episodes` : null)
  const series = useQuery<SeriesBrief[]>(pageId ? `/pages/${pageId}/series` : null)

  const setP = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }
  // the first episode / series of a page is picked for the owner
  useEffect(() => {
    if (what === 'episode' && !episodeId && eps.data?.length) setP({ episode: String(eps.data[0].id) })
    if (what === 'series' && !seriesId && series.data?.length) setP({ series: String(series.data[0].id) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [what, episodeId, seriesId, eps.data, series.data])

  const target: CoverTarget | null = useMemo(() => {
    if (!pageId) return null
    if (what === 'banner') return { page: pageId, kind: 'banner' }
    if (what === 'series') return seriesId ? { page: pageId, series: seriesId, kind: 'series' } : null
    return episodeId ? { page: pageId, episode: episodeId, kind: 'episode' } : null
  }, [pageId, what, episodeId, seriesId])

  if (pages.loading && !pages.data) return <Loading />
  if (!pages.data?.length) return <Empty icon="image" title={t('cv.title')} text={t('cv.no_pages')} />
  return (
    <div className="stack">
      <PageHead title={t('cv.title')} />
      <Notice tone="info">{t('cv.intro')}</Notice>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <SelectField
          className="grow"
          label={t('cv.pick_page')}
          value={String(pageId)}
          onChange={(v) => setP({ page: v, episode: null, series: null })}
          options={pages.data.map((p) => ({ value: String(p.id), label: p.name }))}
        />
        <div className="field">
          <span className="field-label">{t('cv.pick_what')}</span>
          <Segmented<What>
            label={t('cv.pick_what')}
            value={what}
            onChange={(k) => setP({ what: k, episode: null, series: null })}
            options={[
              { key: 'episode', label: t('cv.what_episode') },
              { key: 'series', label: t('cv.what_series') },
              { key: 'banner', label: t('cv.what_banner') },
            ]}
          />
        </div>
      </div>
      {what === 'episode' &&
        (eps.data && eps.data.length === 0 ? (
          <Notice tone="warn">{t('cv.no_episodes')}</Notice>
        ) : (
          <SelectField
            label={t('cv.pick_episode')}
            value={episodeId ? String(episodeId) : ''}
            onChange={(v) => setP({ episode: v })}
            options={[{ value: '', label: t('cv.pick_ph') }, ...(eps.data ?? []).map((e) => ({ value: String(e.id), label: `${e.series_title ?? ''} · ${t('cv.target_episode', { n: e.number, title: e.title })}` }))]}
          />
        ))}
      {what === 'series' &&
        (series.data && series.data.length === 0 ? (
          <Notice tone="warn">{t('cv.no_series')}</Notice>
        ) : (
          <SelectField
            label={t('cv.pick_series')}
            value={seriesId ? String(seriesId) : ''}
            onChange={(v) => setP({ series: v })}
            options={[{ value: '', label: t('cv.pick_ph') }, ...(series.data ?? []).map((s) => ({ value: String(s.id), label: s.title }))]}
          />
        ))}
      {target ? <CoverStudio key={`${target.page}-${target.episode ?? 0}-${target.series ?? 0}-${target.kind}`} target={target} /> : null}
    </div>
  )
}
