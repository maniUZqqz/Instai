import { useCallback, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Empty, LinkButton, Loading, SelectField } from '../components/ui'
import { useQuery } from '../hooks'
import type { PageLite } from './api'
import type { EpisodeBrief } from './api2'
import { useL } from './useL'

function useParamSetter() {
  const [params, setParams] = useSearchParams()
  const set = useCallback(
    (next: Record<string, number | null>) => {
      const p = new URLSearchParams(params)
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, String(v))
        else p.delete(k)
      }
      setParams(p, { replace: true })
    },
    [params, setParams],
  )
  return { params, set }
}

/** Page picker kept in the URL (?page=). Renders `children(page)` once a page is chosen; shows the empty state itself. */
export function PagePicker({ children, extra }: { children: (page: PageLite) => ReactNode; extra?: ReactNode }) {
  const { s } = useL()
  const { params, set } = useParamSetter()
  const pages = useQuery<PageLite[]>('/pages')
  if (pages.loading) return <Loading />
  if (!pages.data || pages.data.length === 0) {
    return <Empty icon="pages" title={s('pick.no_pages')} text={s('pick.no_pages_text')} action={<LinkButton to="/pages/new" variant="primary" icon="plus">{s('pick.new_page')}</LinkButton>} />
  }
  const want = Number(params.get('page')) || null
  const page = pages.data.find((p) => p.id === want) ?? pages.data[0]
  return (
    <div className="stack-lg">
      <div className="card flat">
        <div className="grid-2">
          <SelectField label={s('pick.page')} value={String(page.id)} onChange={(v) => set({ page: Number(v) })} options={pages.data.map((p) => ({ value: String(p.id), label: p.name }))} />
          {extra}
        </div>
      </div>
      {children(page)}
    </div>
  )
}

/** Page + episode pickers kept in the URL (?page=&episode=). */
export function EpisodePicker({ children }: { children: (page: PageLite, episode: EpisodeBrief) => ReactNode }) {
  return <PagePicker>{(page) => <EpisodeForPage page={page}>{children}</EpisodeForPage>}</PagePicker>
}

/** Episode picker (?episode=) for an already chosen page. */
export function EpisodeForPage({ page, children }: { page: PageLite; children: (page: PageLite, episode: EpisodeBrief) => ReactNode }) {
  const { params, set } = useParamSetter()
  return <EpisodeSelect page={page} params={params} set={set}>{children}</EpisodeSelect>
}

function EpisodeSelect({ page, params, set, children }: { page: PageLite; params: URLSearchParams; set: (n: Record<string, number | null>) => void; children: (page: PageLite, ep: EpisodeBrief) => ReactNode }) {
  const { s } = useL()
  const eps = useQuery<EpisodeBrief[]>(`/pages/${page.id}/episodes`)
  if (eps.loading) return <Loading />
  if (!eps.data || eps.data.length === 0) {
    return <Empty icon="film" title={s('pick.no_episodes')} text={s('pick.no_episodes_text')} action={<LinkButton to={`/pages/${page.id}`} icon="pages">{s('pick.open_page')}</LinkButton>} />
  }
  const want = Number(params.get('episode')) || null
  const ep = eps.data.find((e) => e.id === want) ?? eps.data[0]
  return (
    <div className="stack-lg">
      <div className="card flat">
        <SelectField
          label={s('pick.episode')}
          value={String(ep.id)}
          onChange={(v) => set({ episode: Number(v) })}
          options={eps.data.map((e) => ({ value: String(e.id), label: `${e.series_title} · ${e.number}. ${e.title} (${e.state_label})` }))}
        />
      </div>
      {children(page, ep)}
    </div>
  )
}
