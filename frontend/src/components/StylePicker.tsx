import { useMemo, useRef, useState } from 'react'
import type { StylePreset, Suit, ThemePreset } from '../api/types'
import { desc, nm, paletteGradient, styleImage, styleMatches, useLibrary, vocab } from '../library'
import { useI18n } from '../i18n'
import { ErrorState, Loading, Badge, Segmented } from './ui'

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

/** The search / group / suitability filter of the style gallery, shared by the picker and the library page. */
export function useStyleFilter(styles: StylePreset[]) {
  const [group, setGroup] = useState('')
  const [suit, setSuit] = useState<'' | Suit>('')
  const [q, setQ] = useState('')
  const list = useMemo(() => styles.filter((s) => (!group || s.group === group) && (!suit || (s.suitability ?? []).includes(suit)) && styleMatches(s, q)), [styles, group, suit, q])
  return { group, setGroup, suit, setSuit, q, setQ, list }
}

/** Group chips (with counts), a "suits image / video / character" switch and the search box. The chips are the `.filter-chip`s of the gallery. */
export function StyleFilters({ styles, f, name }: { styles: StylePreset[]; f: ReturnType<typeof useStyleFilter>; name: string }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const groups = lib.data?.groups ?? []
  const counts = (k: string) => styles.filter((s) => s.group === k).length
  return (
    <div className="stack-sm">
      <div className="field-label" id={`${name}-group`}>{t('lib.group')}</div>
      <div className="filter-chips" role="group" aria-labelledby={`${name}-group`}>
        <button type="button" className={'filter-chip' + (f.group === '' ? ' on' : '')} aria-pressed={f.group === ''} onClick={() => f.setGroup('')}>
          {t('lib.all')} <span className="muted">({styles.length})</span>
        </button>
        {groups.map((g) => (
          <button key={g.key} type="button" className={'filter-chip' + (f.group === g.key ? ' on' : '')} aria-pressed={f.group === g.key} onClick={() => f.setGroup(g.key)}>
            {lang === 'fa' ? g.fa : g.en} <span className="muted">({counts(g.key)})</span>
          </button>
        ))}
      </div>
      <div className="row">
        <Segmented
          label={t('lib.suits')}
          value={f.suit}
          onChange={(v) => f.setSuit(v)}
          options={[
            { key: '' as '' | Suit, label: t('lib.suits_any') },
            { key: 'image' as '' | Suit, label: t('lib.suits_image') },
            { key: 'video' as '' | Suit, label: t('lib.suits_video') },
            { key: 'character' as '' | Suit, label: t('lib.suits_character') },
          ]}
        />
        <div className="field" style={{ flex: '1 1 14rem' }}>
          <label htmlFor={`${name}-q`} className="sr-only">{t('lib.search')}</label>
          <input id={`${name}-q`} type="search" value={f.q} onChange={(e) => f.setQ(e.target.value)} placeholder={t('lib.search')} />
        </div>
      </div>
    </div>
  )
}

/** Choose a style from the art/animation library and a colour theme (the project's / page's look). Used by the wizard, the page settings, the series
 *  look and "start a project from an idea". */
export function StylePicker({ value, onChange, showTheme = true, name = 'look', scroll = false }: { value: Look; onChange: (v: Look) => void; showTheme?: boolean; name?: string; scroll?: boolean }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const themeTouched = useRef(false)
  const styles = lib.data?.styles ?? []
  const f = useStyleFilter(styles)
  if (lib.error) return <ErrorState error={lib.error} onRetry={lib.reload} />
  if (!lib.data) return <Loading />
  const L = lib.data
  const sel: StylePreset | undefined = styles.find((s) => s.key === value.style_key)
  const pick = (s: StylePreset) => onChange({ style_key: s.key, realism: s.realism, theme_key: themeTouched.current && value.theme_key ? value.theme_key : s.theme_key })
  const themes = L.themes
  return (
    <div className="stack">
      <StyleFilters styles={styles} f={f} name={name} />

      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="sr-only">{t('lib.styles')}</legend>
        <div className={'choice-grid style-grid' + (scroll ? ' scroll-box' : '')}>
          {f.list.map((s) => (
            <label key={s.key} className={'choice style-card' + (value.style_key === s.key ? ' selected' : '')}>
              <input type="radio" name={`${name}-style`} checked={value.style_key === s.key} onChange={() => pick(s)} />
              <Swatch palette={s.palette} url={styleImage(s)} />
              <span className="strong">{nm(s, lang)}</span>
              <span className="small muted">{vocab(L.groups, s.group, lang)}</span>
              {s.known_as && <span className="small ltr known-as">{'≈ ' + s.known_as}</span>}
              {!s.builtin && <Badge tone="info">{t('lib.mine')}</Badge>}
            </label>
          ))}
          {f.list.length === 0 && <p className="muted">{t('lib.none_found')}</p>}
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

const SUIT_KEY: Record<Suit, 'lib.suits_image' | 'lib.suits_video' | 'lib.suits_character'> = { image: 'lib.suits_image', video: 'lib.suits_video', character: 'lib.suits_character' }

export function StyleDetails({ style: s }: { style: StylePreset }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const th: ThemePreset | undefined = lib.theme(s.theme_key)
  const g = s.gen
  return (
    <div className="card soft flat stack-sm" aria-live="polite">
      <div className="row between">
        <h3>{nm(s, lang)}</h3>
        <div className="row">
          {s.group && <Badge>{vocab(lib.data?.groups, s.group, lang)}</Badge>}
          <Badge>{vocab(lib.data?.realism, s.realism, lang)}</Badge>
          <Badge tone="info">{vocab(lib.data?.animations, s.animation, lang)}</Badge>
          <Badge>{t('lib.fps_feel', { n: s.fps_feel })}</Badge>
        </div>
      </div>
      <p>{desc(s, lang)}</p>
      <div className="row">
        <span className="small muted">{t('lib.suits')}:</span>
        {(s.suitability ?? []).map((x) => <Badge key={x} tone="ok">{t(SUIT_KEY[x])}</Badge>)}
      </div>
      {s.known_as && <p className="small muted" data-testid="known-as" title={t('lib.known_as_note')}>{t('lib.known_as')}: <span className="ltr strong">{s.known_as}</span></p>}
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
      {g && (
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>{t('lib.gen_hints')}</summary>
          <dl className="kv small" style={{ marginBlockStart: '0.5rem' }}>
            <dt>{t('lib.gen_model')}</dt>
            <dd>{t(('lib.model_' + g.model) as 'lib.model_flux_dev')}{g.alt_model ? ` / ${t(('lib.model_' + g.alt_model) as 'lib.model_flux_dev')}` : ''}</dd>
            <dt>{t('lib.gen_steps')}</dt><dd className="ltr">{g.steps}</dd>
            <dt>{t('lib.gen_cfg')}</dt><dd className="ltr">{g.model === 'sdxl_anime' ? `CFG ${g.cfg}` : `guidance ${g.guidance}`}</dd>
            <dt>{t('lib.gen_sampler')}</dt><dd className="ltr">{g.sampler} / {g.scheduler}</dd>
            <dt>{t('lib.gen_aspect')}</dt><dd className="ltr">{g.aspect}</dd>
            {g.lora.length > 0 && (<><dt>{t('lib.gen_lora')}</dt><dd className="ltr">{g.lora.join('; ')}</dd></>)}
          </dl>
          <p className="small muted">{t('lib.gen_note')}</p>
        </details>
      )}
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
