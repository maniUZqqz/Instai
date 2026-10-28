import { useMemo, useRef, useState } from 'react'
import type { StylePreset, ThemePreset } from '../api/types'
import { desc, nm, paletteGradient, useLibrary, vocab } from '../library'
import { useI18n } from '../i18n'
import { ErrorState, Loading, Badge } from './ui'

export interface Look {
  style_key: string
  realism: string
  theme_key: string
}

export function Swatch({ palette, url, height = 56 }: { palette: string[]; url?: string | null; height?: number }) {
  return (
    <div className="swatch" style={{ height, background: url ? `center / cover no-repeat url(${url})` : paletteGradient(palette) }} aria-hidden="true">
      {!url && (
        <div className="swatch-chips">
          {palette.slice(0, 6).map((c, i) => (
            <i key={i} style={{ background: c }} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Choose a realism level, a concrete style preset and a theme from the library (page look). Used by the wizard, the page settings and series overrides. */
export function StylePicker({ value, onChange, showTheme = true, name = 'look' }: { value: Look; onChange: (v: Look) => void; showTheme?: boolean; name?: string }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const [realism, setRealism] = useState('')
  const [q, setQ] = useState('')
  const themeTouched = useRef(false)
  const styles = lib.data?.styles ?? []
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return styles.filter((s) => (!realism || s.realism === realism) && (!needle || [s.name_fa, s.name_en, s.description_en, s.description_fa, ...s.tags].join(' ').toLowerCase().includes(needle)))
  }, [styles, realism, q])
  if (lib.error) return <ErrorState error={lib.error} onRetry={lib.reload} />
  if (!lib.data) return <Loading />
  const L = lib.data
  const sel: StylePreset | undefined = styles.find((s) => s.key === value.style_key)
  const counts = (k: string) => styles.filter((s) => s.realism === k).length
  const pick = (s: StylePreset) => onChange({ style_key: s.key, realism: s.realism, theme_key: themeTouched.current && value.theme_key ? value.theme_key : s.theme_key })
  const themes = L.themes
  return (
    <div className="stack">
      <div className="stack-sm">
        <div className="field-label" id={`${name}-realism`}>{t('lib.realism')}</div>
        <div className="filter-chips" role="group" aria-labelledby={`${name}-realism`}>
          <button type="button" className={'filter-chip' + (realism === '' ? ' on' : '')} aria-pressed={realism === ''} onClick={() => setRealism('')}>
            {t('lib.all')} <span className="muted">({styles.length})</span>
          </button>
          {L.realism.map((r) => (
            <button key={r.key} type="button" className={'filter-chip' + (realism === r.key ? ' on' : '')} aria-pressed={realism === r.key} onClick={() => setRealism(r.key)}>
              {lang === 'fa' ? r.fa : r.en} <span className="muted">({counts(r.key)})</span>
            </button>
          ))}
        </div>
        <div className="field">
          <label htmlFor={`${name}-q`} className="sr-only">{t('lib.search')}</label>
          <input id={`${name}-q`} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('lib.search')} />
        </div>
      </div>

      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="sr-only">{t('lib.styles')}</legend>
        <div className="choice-grid style-grid">
          {list.map((s) => (
            <label key={s.key} className={'choice style-card' + (value.style_key === s.key ? ' selected' : '')}>
              <input type="radio" name={`${name}-style`} checked={value.style_key === s.key} onChange={() => pick(s)} />
              <Swatch palette={s.palette} url={s.thumbnail_url} />
              <span className="strong">{nm(s, lang)}</span>
              <span className="small muted">
                {vocab(L.animations, s.animation, lang)}
              </span>
              {!s.builtin && <Badge tone="info">{t('lib.mine')}</Badge>}
            </label>
          ))}
          {list.length === 0 && <p className="muted">{t('lib.none_found')}</p>}
        </div>
      </fieldset>

      {sel && <StyleDetails style={sel} />}

      {showTheme && (
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field-label">{t('lib.theme')}</legend>
          <p className="field-hint">{t('lib.theme_hint')}</p>
          <div className="choice-grid theme-grid">
            {themes.map((th) => (
              <label key={th.key} className={'choice theme-card' + (value.theme_key === th.key ? ' selected' : '')}>
                <input
                  type="radio"
                  name={`${name}-theme`}
                  checked={value.theme_key === th.key}
                  onChange={() => {
                    themeTouched.current = true
                    onChange({ ...value, theme_key: th.key })
                  }}
                />
                <Swatch palette={th.palette} height={34} />
                <span className="strong small">{nm(th, lang)}</span>
                <span className="small muted">{th.mood}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
    </div>
  )
}

export function StyleDetails({ style: s }: { style: StylePreset }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const th: ThemePreset | undefined = lib.theme(s.theme_key)
  return (
    <div className="card soft flat stack-sm" aria-live="polite">
      <div className="row between">
        <h3>{nm(s, lang)}</h3>
        <div className="row">
          <Badge>{vocab(lib.data?.realism, s.realism, lang)}</Badge>
          <Badge tone="info">{vocab(lib.data?.animations, s.animation, lang)}</Badge>
          <Badge>{t('lib.fps_feel', { n: s.fps_feel })}</Badge>
        </div>
      </div>
      <p>{desc(s, lang)}</p>
      <div className="row">
        {s.palette.map((c, i) => (
          <span key={i} className="chip-color" title={c}>
            <i style={{ background: c }} /> <span className="ltr small">{c}</span>
          </span>
        ))}
      </div>
      <dl className="kv small">
        {s.lighting && (<><dt>{t('lib.lighting')}</dt><dd>{s.lighting}</dd></>)}
        {s.mood && (<><dt>{t('lib.mood')}</dt><dd>{s.mood}</dd></>)}
        <dt>{t('lib.techniques')}</dt>
        <dd className="row">{s.techniques.map((x) => <Badge key={x}>{t(('tech.' + x) as 'tech.still_kenburns')}</Badge>)}</dd>
        {th && (<><dt>{t('lib.default_theme')}</dt><dd>{nm(th, lang)}</dd></>)}
      </dl>
      <details>
        <summary className="small" style={{ cursor: 'pointer' }}>{t('lib.prompts')}</summary>
        <dl className="kv small ltr" style={{ marginBlockStart: '0.5rem' }}>
          <dt>{t('lib.image_pos')}</dt><dd>{s.image_positive}</dd>
          <dt>{t('lib.image_neg')}</dt><dd>{s.image_negative}</dd>
          <dt>{t('lib.video_pos')}</dt><dd>{s.video_positive}</dd>
          <dt>{t('lib.video_neg')}</dt><dd>{s.video_negative}</dd>
          <dt>{t('lib.sample')}</dt><dd>{s.sample_prompt}</dd>
        </dl>
      </details>
    </div>
  )
}
