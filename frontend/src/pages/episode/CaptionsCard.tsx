import { useState } from 'react'
import { api } from '../../api/client'
import type { CaptionCatalogue, CaptionConfig, Episode, EpisodeCaptions } from '../../api/types'
import { CaptionPicker } from '../../components/CaptionPicker'
import { Icon } from '../../components/Icon'
import { Badge, Button, Card, Notice } from '../../components/ui'
import { useAction, useQuery } from '../../hooks'
import { useI18n } from '../../i18n'

/** The captions of ONE episode: the page's choice shows through until the episode picks its own; changing it re-joins the video (keyframes, narration and shot clips are reused). */
export function CaptionsCard({ ep, locked, onChanged }: { ep: Episode; locked: boolean; onChanged: () => void }) {
  const { t, lang } = useI18n()
  const act = useAction()
  const cat = useQuery<CaptionCatalogue>('/captions')
  const cap: EpisodeCaptions | undefined = ep.captions
  const [open, setOpen] = useState(false)          // the eight previews are drawn by ffmpeg: ask for them only when the owner opens the picker
  if (!cap) return null
  const own = Object.keys(cap.override).length > 0
  const name = (key?: string) => {
    const row = cat.data?.presets.find((p) => p.key === key)
    return row ? (lang === 'en' ? row.en : row.fa) : key ?? ''
  }
  const zoneName = (key?: string) => {
    const row = cat.data?.zones.find((z) => z.key === key)
    return row ? (lang === 'en' ? row.en : row.fa) : key ?? ''
  }
  const modeName = (key?: string) => {
    const row = cat.data?.modes.find((m) => m.key === key)
    return row ? (lang === 'en' ? row.en : row.fa) : key ?? ''
  }
  const save = async (v: CaptionConfig) => {
    const diff: Partial<CaptionConfig> = {}
    for (const k of ['preset', 'mode', 'zone'] as const) if (v[k] !== cap.page[k]) diff[k] = v[k]
    const r = await act.run(() => api.put(`/episodes/${ep.id}/captions`, diff), { success: t('cap.ep_saved') })
    if (r) onChanged()
  }
  const reset = async () => {
    const r = await act.run(() => api.del<EpisodeCaptions>(`/episodes/${ep.id}/captions`), { success: t('cap.ep_saved') })
    if (r) onChanged()
  }
  const info = cap.info
  return (
    <Card title={t('cap.ep_title')} actions={<Badge tone={own ? 'info' : 'neutral'}>{own ? t('cap.ep_own') : t('cap.ep_from_page')}</Badge>}>
      <div className="stack" data-testid="captions-card">
        <p className="muted small">{t('cap.ep_intro')}</p>
        {locked && <Notice tone="info">{t('cap.ep_locked')}</Notice>}
        <p data-testid="captions-current">
          <span className="strong">{name(cap.effective.preset)}</span> · {modeName(cap.effective.mode)} · {t('cap.ep_zone')}: {zoneName(cap.effective.zone)}
        </p>
        <div className="row">
          <Button size="sm" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="captions-toggle">
            {open ? t('cap.ep_close') : t('cap.ep_open')}
          </Button>
        </div>
        {open && <CaptionPicker scope={{ episode: ep.id }} value={cap.effective} onChange={save} disabled={locked || act.busy} />}
        <div className="row">
          {own && (
            <Button size="sm" busy={act.busy} disabled={locked} onClick={reset}>
              {t('cap.ep_reset')}
            </Button>
          )}
          {cap.srt_url && (
            <a href={cap.srt_url} download className="btn sm">
              <Icon name="download" />
              {t('cap.ep_srt')}
            </a>
          )}
        </div>
        {info && info.preset && (
          <p className="small muted">
            {t('cap.ep_last')}: {name(info.preset)} · {t('cap.ep_zone')}: {zoneName(info.zone)}{' '}
            <Badge tone={info.estimated ? 'warn' : 'ok'}>{info.estimated ? t('cap.est_yes') : t('cap.est_no')}</Badge>
          </p>
        )}
        <p className="small muted">{t('cap.ep_rebuild')}</p>
      </div>
    </Card>
  )
}
