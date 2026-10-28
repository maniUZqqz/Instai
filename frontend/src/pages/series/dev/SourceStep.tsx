import { useState } from 'react'
import { api } from '../../../api/client'
import type { Development, SourceCandidate, SourceSearchResult } from '../../../api/types'
import { AreaField, Badge, Button, Card, CheckField, Notice, TextField } from '../../../components/ui'
import { useApp } from '../../../components/Shell'
import { useAction, useJobRunner } from '../../../hooks'
import { useI18n } from '../../../i18n'
import { LocalJob, StepFrame, type StepProps } from './common'

const PROVIDERS = ['anilist', 'wikipedia', 'fandom', 'jikan'] as const

export function SourceStep(p: StepProps) {
  const { t, f, lang } = useI18n()
  const { dev, setDev } = p
  const [query, setQuery] = useState(dev.source.title ?? '')
  const [prov, setProv] = useState<string[]>(['anilist', 'wikipedia'])
  const [fandom, setFandom] = useState(dev.source.fandom_wiki ?? '')
  const [result, setResult] = useState<SourceSearchResult | null>(null)
  const [manual, setManual] = useState({ title: '', notes: '' })
  const [showManual, setShowManual] = useState(false)
  const act = useAction()
  const { demo } = useApp()
  const runner = useJobRunner<SourceSearchResult>({ onSucceeded: (j) => setResult(j.result as SourceSearchResult) })
  const search = () =>
    runner.start(() => api.post(`/series/${dev.series.id}/source/search`, { query: query.trim(), providers: demo ? [] : prov, fandom_wiki: fandom.trim(), language: 'en' }))
  const choose = async (c: SourceCandidate) => {
    const d = await act.run(() => api.post<Development>(`/series/${dev.series.id}/source`, { candidate: { ...c, fandom_wiki: fandom.trim() } }))
    if (d) {
      setDev(d)
      setResult(null)
    }
  }
  const useManual = async () => {
    const d = await act.run(() => api.post<Development>(`/series/${dev.series.id}/source`, { manual: true, title: manual.title.trim(), notes: manual.notes, fandom_wiki: fandom.trim() }))
    if (d) {
      setDev(d)
      setShowManual(false)
    }
  }
  const clear = async () => {
    const d = await act.run(() => api.post<Development>(`/series/${dev.series.id}/source/clear`, {}))
    if (d) setDev(d)
  }
  const src = dev.source
  return (
    <StepFrame {...p}>
      {src.title && (
        <Card title={t('src.chosen')} actions={<Button size="sm" onClick={clear} busy={act.busy}>{t('dev.change')}</Button>}>
          <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
            {src.cover_url && <img src={src.cover_url} alt="" className="cover-thumb" loading="lazy" referrerPolicy="no-referrer" />}
            <div className="stack-sm">
              <div className="strong">{src.title}</div>
              <div className="row small muted">
                {src.provider && <Badge>{src.provider}</Badge>}
                {src.manual && <Badge>{t('src.manual')}</Badge>}
                {src.year ? <span>{src.year}</span> : null}
                {src.format ? <span>{src.format}</span> : null}
                {src.episodes ? <span>{t('series.episodes_n', { n: f.num(src.episodes) })}</span> : null}
              </div>
              {src.description && <p className="small">{src.description}</p>}
              {src.notes && <p className="small pre">{src.notes}</p>}
              {src.url && <a className="small ltr" href={src.url} target="_blank" rel="noreferrer noopener">{src.url}</a>}
            </div>
          </div>
        </Card>
      )}
      {dev.series.is_fan_content && dev.series.notices.map((n) => <Notice key={n.key} tone="warn">{lang === 'en' ? n.text_en ?? n.text : n.text}</Notice>)}

      <Card title={t('src.search_title')}>
        <div className="stack">
          <p className="muted small">{t('src.search_intro')}</p>
          {demo && <Notice tone="info">{t('src.demo_note')}</Notice>}
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <TextField className="grow" label={t('src.query')} ltr value={query} onChange={setQuery} placeholder={t('src.query_ph')} onKeyDown={(e) => e.key === 'Enter' && query.trim() && !runner.busy && search()} />
            <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} disabled={!query.trim() || prov.length === 0} onClick={search}>{t('src.search')}</Button>
          </div>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field-label">{t('src.providers')}</legend>
            <div className="row">
              {PROVIDERS.map((x) => (
                <CheckField key={x} label={t(('src.prov_' + x) as 'src.prov_anilist')} hint={x === 'jikan' ? t('src.prov_jikan_hint') : undefined} checked={prov.includes(x)} onChange={(on) => setProv(on ? [...prov, x] : prov.filter((y) => y !== x))} />
              ))}
            </div>
          </fieldset>
          {prov.includes('fandom') && <TextField label={t('src.fandom_wiki')} ltr value={fandom} onChange={setFandom} placeholder="jujutsu-kaisen" hint={t('src.fandom_hint')} />}
          <Notice tone="info">{t('src.terms_note')}</Notice>
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
          {result && (
            <div className="stack">
              {result.errors.length > 0 && (
                <Notice tone="warn">
                  <div className="stack-sm">
                    <div className="strong">{t('src.errors')}</div>
                    <ul className="small" style={{ margin: 0, paddingInlineStart: '1.25rem' }}>
                      {result.errors.map((e, i) => <li key={i} className="ltr">{e.message}</li>)}
                    </ul>
                    <div className="small">{t('src.errors_hint')}</div>
                  </div>
                </Notice>
              )}
              {result.candidates.length === 0 && result.errors.length === 0 && <p className="muted">{t('src.none')}</p>}
              <div className="grid-auto">
                {result.candidates.map((c) => (
                  <div key={c.provider + c.id} className="card soft flat stack-sm cand">
                    <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                      {c.cover_url && <img src={c.cover_url} alt="" className="cover-thumb" loading="lazy" referrerPolicy="no-referrer" />}
                      <div className="stack-sm">
                        <div className="strong">{c.title}</div>
                        {c.title_native && <div className="small muted">{c.title_native}</div>}
                        <div className="row small muted">
                          <Badge>{c.provider}</Badge>
                          {c.year ? <span>{c.year}</span> : null}
                          {c.format ? <span>{c.format}</span> : null}
                          {c.episodes ? <span>{t('series.episodes_n', { n: f.num(c.episodes) })}</span> : null}
                        </div>
                      </div>
                    </div>
                    {c.genres.length > 0 && <div className="row">{c.genres.map((g) => <Badge key={g}>{g}</Badge>)}</div>}
                    {c.description && <p className="small cand-desc">{c.description}</p>}
                    <div className="row">
                      <Button size="sm" variant="primary" icon="check" busy={act.busy} onClick={() => choose(c)}>{t('src.use')}</Button>
                      {c.url && <a className="btn sm" href={c.url} target="_blank" rel="noreferrer noopener">{t('src.open')}</a>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card title={t('src.manual_title')} actions={<Button size="sm" onClick={() => setShowManual((s) => !s)} aria-expanded={showManual}>{showManual ? t('common.cancel') : t('src.manual_open')}</Button>}>
        {showManual ? (
          <div className="stack">
            <p className="muted small">{t('src.manual_intro')}</p>
            <TextField label={t('src.manual_name')} required value={manual.title} onChange={(v) => setManual({ ...manual, title: v })} />
            <AreaField label={t('src.manual_notes')} value={manual.notes} onChange={(v) => setManual({ ...manual, notes: v })} hint={t('src.manual_notes_hint')} />
            <div><Button variant="primary" icon="check" busy={act.busy} disabled={!manual.title.trim()} onClick={useManual}>{t('src.manual_use')}</Button></div>
          </div>
        ) : (
          <p className="muted small">{t('src.manual_collapsed')}</p>
        )}
      </Card>
    </StepFrame>
  )
}
