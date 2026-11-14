import { useState } from 'react'
import type { ModelRow, ModelsPayload } from '../api/types'
import { Async, Badge, CardSkeletons, Link, type Tone } from '../components/ui'
import { useQuery } from '../hooks'
import { useI18n } from '../i18n'

// The licence of every model and tool InstAI can use, and the image / video workflows with what each one still misses. It used to sit inside the Settings page
// (together with a second copy of the download catalogue, which made that page 15 000 px tall); installing is done on the Downloads page only.
const COMMERCIAL: Record<string, { tone: Tone; key: 'lic.yes' | 'lic.conditional' | 'lic.no' | 'lic.unknown' }> = {
  yes: { tone: 'ok', key: 'lic.yes' },
  conditional: { tone: 'warn', key: 'lic.conditional' },
  no: { tone: 'err', key: 'lic.no' },
  unknown: { tone: 'neutral', key: 'lic.unknown' },
}

/** A closed card; the list (one request, a few seconds of work for the server) is fetched only when it is opened. */
export function LicencesFold() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <details className="card fold" data-testid="fold-licences" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        <span className="strong">{t('set.models_title')}</span>
        <span className="small muted">{t('set.models_fold_hint')}</span>
      </summary>
      {open && <LicencesBody />}
    </details>
  )
}

function LicencesBody() {
  const { t, f } = useI18n()
  const q = useQuery<ModelsPayload>('/models')
  return (
    <div className="stack-lg">
      <p className="muted">{t('set.models_intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={2} />}>
        {(m) => {
          const rows = [...m.models].sort((a, b) => Number(!!a.excluded) - Number(!!b.excluded))
          return (
            <>
              <section className="stack" aria-label={t('set.licences_title')}>
                <h3>{t('set.licences_title')}</h3>
                <p className="small muted">{t('set.licences_note', { date: m.checked_on })}</p>
                <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 330px), 1fr))' }}>
                  {rows.map((r) => (
                    <ModelCard key={r.id} r={r} size={r.package ? m.packages[r.package]?.size : undefined} />
                  ))}
                </div>
              </section>

              {m.workflows.length > 0 && (
                <section className="stack" aria-label={t('set.workflows_title')}>
                  <h3>{t('set.workflows_title')}</h3>
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>{t('set.wf_name')}</th>
                          <th>{t('set.wf_kind')}</th>
                          <th>{t('set.wf_vram')}</th>
                          <th>{t('set.wf_licence')}</th>
                          <th>{t('set.wf_available')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {m.workflows.map((w) => (
                          <tr key={w.id}>
                            <td><div className="strong">{w.title}</div><div className="small muted ltr">{w.id}</div></td>
                            <td className="ltr">{w.kind}</td>
                            <td>{w.vram_gb != null ? `${f.num(w.vram_gb)} GB` : '—'}</td>
                            <td className="small">{w.licence} <Badge tone={w.licence_status === 'verified' ? 'ok' : 'warn'}>{w.licence_status}</Badge></td>
                            <td>{w.available == null ? <Badge>{t('set.wf_unknown')}</Badge> : w.available ? <Badge tone="ok">{t('set.wf_ready')}</Badge> : <Badge tone="warn" title={w.missing.join(', ')}>{t('set.wf_missing', { n: w.missing.length })}</Badge>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )
        }}
      </Async>
    </div>
  )
}

function ModelCard({ r, size }: { r: ModelRow; size: number | undefined }) {
  const { t, f } = useI18n()
  const c = COMMERCIAL[r.commercial] ?? COMMERCIAL.unknown
  const verified = r.verified === null ? null : r.verified === 'brief' ? t('lic.verified_brief') : r.verified
  return (
    <div className={'card flat stack-sm' + (r.excluded ? ' soft' : '')} style={r.excluded ? { opacity: 0.85 } : undefined}>
      <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
        <span className="strong" dir="auto">{r.name}</span>
        {r.installed != null && <Badge tone={r.installed ? 'ok' : 'neutral'}>{r.installed ? t('set.installed') : t('set.not_installed')}</Badge>}
      </div>
      <div className="small muted" dir="auto">{r.role}</div>
      <div className="row">
        <Badge tone={c.tone}>{t('lic.commercial')}: {t(c.key)}</Badge>
        {r.excluded && <Badge tone="err">{t('lic.excluded')}</Badge>}
        {r.decision && <Badge tone="warn">{t('lic.decision')}</Badge>}
      </div>
      <div className="small"><span className="muted">{t('lic.licence')}:</span> <bdi>{r.licence}</bdi></div>
      <div className="small">
        <span className="muted">{t('lic.verified')}:</span> {verified ? <bdi>{verified}</bdi> : <Badge tone="warn">{t('set.not_verified')}</Badge>}
      </div>
      <div className="small"><span className="muted">VRAM:</span> <bdi>{r.vram}</bdi></div>
      {r.notes && <div className="small muted" dir="auto">{r.notes}</div>}
      {r.package && !r.excluded && r.installed === false && (
        <div className="small">
          <Link to="/downloads">{t('set.install_in_downloads')}{size ? ` (${f.bytes(size)})` : ''}</Link>
        </div>
      )}
    </div>
  )
}
