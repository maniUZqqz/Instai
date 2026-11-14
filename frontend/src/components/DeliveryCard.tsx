import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DeliveryNetworkPlan, DeliveryPlan, PageTarget } from '../api/types'
import { useAction, useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { Icon } from './Icon'
import { Badge, Notice, SwitchField, SelectField, Button, type Tone } from './ui'

const STATUS_TONE: Record<string, Tone> = { ready: 'ok', fit: 'info', needs_aspect: 'warn' }

/** What the publishing package of ONE publication will hold (a file per network of the page, the reason for any missing file) and the caption check.
 *  The check runs on the text that is typed in the box (not only on the saved one) after a short pause; nothing is ever rewritten. */
export function DeliveryCard({ pubId, caption, tags, savedAt }: { pubId: number; caption: string; tags: string[]; savedAt: string }) {
  const { t, tr, f, lang } = useI18n()
  const [plan, setPlan] = useState<DeliveryPlan | null>(null)
  const [failed, setFailed] = useState(false)
  const tagKey = JSON.stringify(tags)
  useEffect(() => {
    let alive = true
    const h = window.setTimeout(() => {
      api
        .post<DeliveryPlan>(`/publications/${pubId}/delivery`, { caption, hashtags: tags })
        .then((d) => {
          if (alive) {
            setPlan(d)
            setFailed(false)
          }
        })
        .catch(() => alive && setFailed(true))
    }, 450)
    return () => {
      alive = false
      window.clearTimeout(h)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pubId, caption, tagKey, savedAt])
  const say = (n: { fa: string; en: string }) => (lang === 'en' ? n.en : n.fa)
  if (failed && !plan) return <Notice tone="warn">{t('dl.failed')}</Notice>
  if (!plan) return <p className="small muted">{t('dl.loading')}</p>
  const src = plan.source
  return (
    <div className="stack-sm" data-testid={`delivery-${pubId}`}>
      <h3 style={{ fontSize: '1rem' }}>{t('dl.title')}</h3>
      {plan.no_targets && <p className="small muted" data-testid="delivery-no-targets">{t('dl.no_targets')}</p>}
      {src.preview && <Notice tone="warn">{t('dl.source_preview')}</Notice>}
      {src.loudness_lufs != null && (
        <p className="small muted" data-testid="delivery-loudness">
          {t('dl.source_loud', { lufs: f.num(src.loudness_lufs, 1), target: f.num(plan.page_lufs) })}
          {src.loudness?.adjusted && src.loudness.before != null ? ' · ' + t('dl.source_loud_fixed', { before: f.num(src.loudness.before, 1), tp: f.num(src.loudness.tp ?? 0, 1) }) : ''}
        </p>
      )}
      {plan.networks.length > 0 && (
        <ul className="qc-list" data-testid="delivery-networks">
          {plan.networks.map((n: DeliveryNetworkPlan) => (
            <li key={n.key} data-testid={`delivery-net-${n.key}`}>
              <span>
                <Badge tone={STATUS_TONE[n.status] ?? 'neutral'}>{tr('dl.status_' + n.status, n.status)}</Badge>
              </span>
              <span>
                <strong>{lang === 'en' ? n.en : n.fa}</strong>
                {n.width && n.height ? <span className="muted small ltr"> · {t('dl.net_spec', { w: String(n.width), h: String(n.height), fps: String(n.fps), lufs: f.num(n.lufs) })}</span> : null}
                {[...n.notes, ...n.warnings].map((x, i) => (
                  <span key={i} className="small muted" style={{ display: 'block' }}>
                    {say(x)}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
      {plan.ignored.map((g) => (
        <p key={g.target} className="small muted">{t('dl.ignored', { platform: g.platform })}</p>
      ))}
      {plan.networks.length > 0 && <p className="small muted">{t('dl.approx')}</p>}
      <h3 style={{ fontSize: '1rem' }}>{t('dl.lint_title')}</h3>
      {plan.lint.length === 0 ? (
        <p className="small" data-testid="lint-ok">
          <Icon name="check" /> {t('dl.lint_ok')}
        </p>
      ) : (
        <ul className="qc-list" data-testid="lint-list">
          {plan.lint.map((w, i) => (
            <li key={i} data-testid={`lint-${w.code}`}>
              <span style={{ color: w.level === 'warn' ? 'var(--warn)' : 'var(--info)' }}>
                <Icon name={w.level === 'warn' ? 'alert' : 'info'} />
                <span className="sr-only">{w.level === 'warn' ? t('dl.level_warn') : t('dl.level_note')}</span>
              </span>
              <span>{lang === 'en' ? w.message_en : w.message}</span>
            </li>
          ))}
        </ul>
      )}
      {plan.hashtags.changed.length > 0 && <p className="small muted">{t('dl.tags_repaired', { tags: plan.hashtags.changed.join('، ') })}</p>}
      <p className="small muted">{t('dl.lint_note')}</p>
    </div>
  )
}

/** The networks a page posts to (its publishing targets): add one of the nine, switch it on or off, and choose the whole-frame-with-blurred-sides delivery for it. */
export function NetworksCard({ pageId, onChanged }: { pageId: number; onChanged?: () => void }) {
  const { t, lang } = useI18n()
  const cat = useQuery<{ networks: { key: string; fa: string; en: string; aspect: string; width: number; height: number; fps: number; lufs: number }[] }>('/delivery/networks')
  const targets = useQuery<PageTarget[]>(`/pages/${pageId}/targets`)
  const act = useAction()
  const [pick, setPick] = useState('')
  const have = new Set((targets.data ?? []).map((x) => x.network))
  const options = (cat.data?.networks ?? []).filter((n) => !have.has(n.key))
  const add = async () => {
    if (!pick) return
    const r = await act.run(() => api.post(`/pages/${pageId}/targets`, { platform: pick }), { success: t('dl.nets_added') })
    if (r) {
      setPick('')
      targets.reload()
      onChanged?.()
    }
  }
  const patch = async (id: number, body: Record<string, unknown>) => {
    await act.run(() => api.patch(`/targets/${id}`, body), { success: t('dl.nets_saved') })
    targets.reload()
    onChanged?.()
  }
  const info = (key: string | null) => (cat.data?.networks ?? []).find((n) => n.key === key)
  return (
    <div className="stack-sm" data-testid="networks-card">
      <p className="small muted">{t('dl.nets_intro')}</p>
      {(targets.data ?? []).length === 0 ? (
        <p className="muted" data-testid="networks-empty">{t('dl.nets_empty')}</p>
      ) : (
        <div className="stack-sm">
          {(targets.data ?? []).map((x) => {
            const n = info(x.network)
            return (
              <div key={x.id} className="card flat stack-sm" data-testid={`network-${x.id}`}>
                <div className="row between">
                  <span className="strong">{lang === 'en' ? x.network_en : x.network_fa}</span>
                  {n && <span className="small muted ltr">{n.aspect} · {n.width}×{n.height} · {n.fps} fps · {n.lufs} LUFS</span>}
                </div>
                <div className="grid-2">
                  <SwitchField label={t('dl.net_enabled')} checked={x.enabled} onChange={(v) => patch(x.id, { enabled: v })} />
                  <SwitchField label={t('dl.net_fit')} hint={t('dl.net_fit_hint')} checked={x.fit === 'blur'} onChange={(v) => patch(x.id, { config: { fit: v ? 'blur' : '' } })} />
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <SelectField className="grow" label={t('dl.nets_add')} value={pick} onChange={setPick}
          options={[{ value: '', label: t('dl.nets_pick') }, ...options.map((n) => ({ value: n.key, label: `${lang === 'en' ? n.en : n.fa} (${n.aspect})` }))]} />
        <Button variant="primary" icon="plus" disabled={!pick} busy={act.busy} onClick={add} data-testid="network-add">
          {t('dl.nets_add')}
        </Button>
      </div>
      <p className="small muted">{t('dl.approx')}</p>
    </div>
  )
}
