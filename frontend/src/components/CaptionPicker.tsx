import { useState, type ReactNode } from 'react'
import type { CaptionCatalogue, CaptionConfig, CaptionMargins, CaptionPreview, CaptionPreviews } from '../api/types'
import { useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { Icon } from './Icon'
import { Badge, CheckField, ErrorState, Loading, Notice, Segmented, SelectField } from './ui'

/** What a page or an episode picks for its captions: the preset (seven of them and the plain look), how they arrive (burned in, a separate file, none) and the platform's safe zone.
 *  The pictures are drawn by the render engine on the server (libass), never imitated with CSS, so the picker shows exactly what the video will have. */
export function CaptionPicker({ scope, value, onChange, disabled, children }: {
  scope: { page?: number; episode?: number }
  value: CaptionConfig
  onChange: (v: CaptionConfig) => void
  disabled?: boolean
  children?: ReactNode
}) {
  const { t, lang } = useI18n()
  const cat = useQuery<CaptionCatalogue>('/captions')
  const [shape, setShape] = useState<'vertical' | 'landscape'>('vertical')
  const [guides, setGuides] = useState(true)
  const qs = scope.episode ? `episode=${scope.episode}` : `page=${scope.page}`
  const prev = useQuery<CaptionPreviews>(cat.data ? `/captions/previews?${qs}&shape=${shape}&zone=${encodeURIComponent(value.zone)}` : null)
  const pick = (row: { fa: string; en: string }) => (lang === 'en' ? row.en : row.fa) || row.fa || row.en
  const hint = (row: { hint_fa: string; hint_en: string }) => (lang === 'en' ? row.hint_en : row.hint_fa) || row.hint_fa || row.hint_en
  if (cat.error) return <ErrorState error={cat.error} onRetry={cat.reload} />
  if (!cat.data) return <Loading />
  const c = cat.data
  const rows: CaptionPreview[] | undefined = prev.data?.previews
  const margins: CaptionMargins | undefined = prev.data?.margins
  const set = (patch: Partial<CaptionConfig>) => onChange({ ...value, ...patch })
  const zone = c.zones.find((z) => z.key === value.zone)
  const mode = c.modes.find((m) => m.key === value.mode)
  const shown = rows ?? c.presets.map((p) => ({ ...p, url: null }) as CaptionPreview)
  return (
    <fieldset className="card soft flat stack" style={{ margin: 0 }} disabled={disabled}>
      <legend className="strong">{t('cap.title')}</legend>
      <p className="muted small">{t('cap.intro')}</p>
      {children}
      <div className="row">
        <Segmented
          label={t('cap.mode')}
          value={value.mode}
          onChange={(k) => set({ mode: k })}
          options={c.modes.map((m) => ({ key: m.key, label: pick(m) }))}
        />
        <Segmented
          label={t('cap.shape')}
          value={shape}
          onChange={setShape}
          options={[{ key: 'vertical', label: t('cap.shape_vertical') }, { key: 'landscape', label: t('cap.shape_landscape') }]}
        />
      </div>
      {mode && <p className="small muted">{hint(mode)}</p>}
      <div className="grid-2">
        <SelectField
          label={t('cap.zone')}
          value={value.zone}
          onChange={(v) => set({ zone: v })}
          options={c.zones.map((z) => ({ value: z.key, label: pick(z) }))}
          hint={<>{zone ? hint(zone) : ''} {t('cap.zone_note')}</>}
        />
        <CheckField label={t('cap.guides')} checked={guides} onChange={setGuides} />
      </div>
      {prev.loading && <Loading label={t('cap.loading')} />}
      {prev.error && <ErrorState error={prev.error} onRetry={prev.reload} />}
      {prev.data && !prev.data.ok && <Notice tone="warn">{t('cap.failed')}</Notice>}
      <div className={'choice-grid cap-grid ' + shape} role="radiogroup" aria-label={t('cap.presets')}>
        {shown.map((row) => {
          const selected = value.preset === row.key
          return (
            <label key={row.key} className={'choice cap-card' + (selected ? ' selected' : '')}>
              <input type="radio" name="caption-preset" checked={selected} onChange={() => set({ preset: row.key })} />
              {selected && <Icon name="check" className="mark" />}
              <span className={'cap-thumb ' + shape} aria-hidden="true">
                {row.url ? <img src={row.url} alt="" loading="lazy" /> : <span className="cap-empty" />}
                {guides && margins && row.url && (
                  <>
                    <i className="cap-guide" style={{ top: 0, left: 0, right: 0, height: `${margins.top * 100}%` }} />
                    <i className="cap-guide" style={{ bottom: 0, left: 0, right: 0, height: `${margins.bottom * 100}%` }} />
                    <i className="cap-guide" style={{ top: `${margins.top * 100}%`, bottom: `${margins.bottom * 100}%`, left: 0, width: `${margins.left * 100}%` }} />
                    <i className="cap-guide" style={{ top: `${margins.top * 100}%`, bottom: `${margins.bottom * 100}%`, right: 0, width: `${margins.right * 100}%` }} />
                  </>
                )}
              </span>
              <span className="strong">{pick(row)}</span>
              <span className="small muted">{hint(row)}</span>
              <span className="row">
                {row.legacy ? <Badge>{t('cap.legacy_badge')}</Badge> : row.contrast ? <Badge tone="ok">{t('cap.contrast', { r: Math.round(row.contrast.text * 10) / 10 })}</Badge> : null}
              </span>
            </label>
          )
        })}
      </div>
      <p className="small muted">{t('cap.look_note')}</p>
      <p className="small muted">{t('cap.estimated_note')}</p>
      <p className="small muted">{t('cap.font_note')}</p>
    </fieldset>
  )
}
