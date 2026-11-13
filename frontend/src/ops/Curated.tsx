import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { Modal } from '../components/feedback'
import { Badge, Button, Card, CheckField, Notice, SelectField, Segmented, type Tone } from '../components/ui'
import { useAction } from '../hooks'
import { useI18n } from '../i18n'
import { ScheduleField } from './ScheduleField'
import type { Catalog, CuratedPackage, When } from './types'

const GROUPS = ['all', 'image', 'control', 'upscale', 'video', 'voice'] as const
type Group = (typeof GROUPS)[number]

const TONE: Record<CuratedPackage['commercial'], Tone> = { yes: 'ok', conditional: 'warn', unknown: 'warn', no: 'err' }

/** The curated, verified model library for the RTX 3060: every package lists its exact files (repository, commit, path, size, sha256,
 *  destination folder, mirror) and what is already on the PC (de-duplicated). Non-commercial / unclear licences are never selected by
 *  default and need a separate confirmation. */
export function CuratedLibrary({ cat, onAdded }: { cat: Catalog; onAdded: () => void }) {
  const { t, lang, f } = useI18n()
  const act = useAction()
  const [group, setGroup] = useState<Group>('all')
  const [picked, setPicked] = useState<string[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [target, setTarget] = useState('local')
  const [ask, setAsk] = useState<CuratedPackage[] | null>(null)
  const when = useRef<When>({ mode: 'now' })
  const list = cat.curated ?? []
  const shown = useMemo(() => list.filter((p) => group === 'all' || p.group === group), [list, group])
  const chosen = list.filter((p) => picked.includes(p.id))
  const total = chosen.reduce((n, p) => n + p.missing_size, 0)
  const targets = cat.targets.map((x) => ({ value: x.id, label: (lang === 'en' ? x.name_en : x.name) + (x.online ? '' : ' — ' + t('ops.node.offline')) }))
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  const commercialLabel = (c: CuratedPackage['commercial']) => t(('cur.comm.' + c) as 'cur.comm.yes')

  const submit = async (confirmLicence: boolean) => {
    const ids = chosen.filter((p) => !p.complete).map((p) => p.id)
    if (!ids.length) return
    const ok = await act.run(() => api.post('/downloads', { packages: ids, target, when: when.current, ...(confirmLicence ? { confirm_licence: true } : {}) }), { success: t('ops.dl.added') })
    if (ok) {
      setPicked([])
      setAsk(null)
      onAdded()
    }
  }
  const go = () => {
    const risky = chosen.filter((p) => p.needs_confirm && !p.complete)
    if (risky.length) setAsk(risky)
    else void submit(false)
  }

  return (
    <Card title={t('cur.title')} className="cur-card" actions={<Badge tone="info">{f.num(list.length)}</Badge>}>
      <div className="stack">
        <Notice tone="info" icon="layers">{t('cur.intro')}</Notice>
        <div className="grid-2">
          <ScheduleField onChange={(w) => { when.current = w }} />
          <SelectField label={t('ops.dl.target')} value={target} onChange={setTarget} options={targets} />
        </div>
        <Segmented<Group> label={t('cur.groups')} value={group} onChange={setGroup} options={GROUPS.map((g) => ({ key: g, label: t(('cur.group.' + g) as 'cur.group.all') }))} />
        {shown.length === 0 && <p className="muted small">{t('cur.empty')}</p>}
        <div className="stack-sm" data-testid="curated-list">
          {shown.map((p) => {
            const isOpen = open === p.id
            const why = (lang === 'en' ? p.why.en : p.why.fa) || ''
            const note = (lang === 'en' ? p.note.en : p.note.fa) || ''
            const state = p.complete ? 'complete' : p.installed > 0 ? 'partial' : 'missing'
            return (
              <div key={p.id} className={'cur-pkg' + (p.needs_confirm ? ' risky' : '')} data-testid={'cur-' + p.id}>
                <div className="cur-head">
                  <CheckField
                    label={<span className="strong ltr" dir="ltr">{p.title}</span>}
                    checked={picked.includes(p.id)}
                    disabled={p.complete}
                    onChange={() => toggle(p.id)}
                  />
                </div>
                <div className="row cur-badges">
                  <Badge tone={TONE[p.commercial]} title={p.licence}>{commercialLabel(p.commercial)}</Badge>
                  <Badge tone={state === 'complete' ? 'ok' : state === 'partial' ? 'warn' : 'neutral'}>
                    {state === 'complete' ? t('cur.state.complete') : state === 'partial' ? t('cur.state.partial', { a: p.installed, b: p.files.length }) : t('cur.state.missing')}
                  </Badge>
                  {p.reused > 0 && <Badge tone="info" title={t('cur.reused_tip')}>{t('cur.reused', { n: p.reused })}</Badge>}
                  <span className="small muted nowrap">{p.complete ? f.bytes(p.size) : t('cur.size_missing', { x: f.bytes(p.missing_size), y: f.bytes(p.size) })}</span>
                  {p.vram && <span className="small muted ltr" dir="ltr">VRAM: {p.vram}</span>}
                </div>
                {why && <p className="small" dir="auto">{why}</p>}
                {p.needs_confirm && <p className="small err-text" dir="auto">{p.commercial === 'no' ? t('cur.warn_nc') : t('cur.warn_unknown')}</p>}
                {note && <p className="small muted" dir="auto">{note}</p>}
                <div className="row">
                  <Button size="sm" icon={isOpen ? 'up' : 'down'} aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : p.id)}>{t('cur.files', { n: p.files.length })}</Button>
                  {p.licence_url && <a className="btn sm" href={p.licence_url} target="_blank" rel="noreferrer noopener">{t('cur.licence_link')}</a>}
                  <span className="small muted" dir="auto">{p.licence} · {t('cur.checked', { d: p.checked })}</span>
                </div>
                {isOpen && (
                  <div className="table-wrap">
                    <table className="table cur-files">
                      <thead><tr><th>{t('cur.col.file')}</th><th>{t('cur.col.folder')}</th><th>{t('cur.col.size')}</th><th>sha256</th><th>{t('cur.col.source')}</th><th>{t('cur.col.state')}</th></tr></thead>
                      <tbody>
                        {p.files.map((x) => (
                          <tr key={x.id}>
                            <td className="ltr" dir="ltr"><div className="strong">{x.name}</div><div className="small muted">{x.title}</div></td>
                            <td className="ltr small" dir="ltr">{x.folder}</td>
                            <td className="nowrap small">{f.bytes(x.size)}</td>
                            <td className="ltr small mono" dir="ltr" title={x.sha256 || t('cur.sha_none')}>{x.sha256 ? x.sha256.slice(0, 16) + '…' : '—'}</td>
                            <td className="ltr small" dir="ltr">
                              {x.repo ? (
                                <>
                                  <a href={x.url} target="_blank" rel="noreferrer noopener">{x.repo}</a>
                                  <div className="muted">{x.path}</div>
                                  {x.mirror && <div className="muted">{t('cur.mirror')}: hf-mirror.com</div>}
                                </>
                              ) : <span className="muted">{x.url.replace(/^https?:\/\//, '').slice(0, 60)}</span>}
                            </td>
                            <td className="small">
                              {x.installed ? <Badge tone={x.reused ? 'info' : 'ok'} title={x.where}>{x.reused ? t('cur.file_reused') : t('cur.file_here')}</Badge> : <Badge>{t('cur.file_missing')}</Badge>}
                              {x.reused && x.where && <div className="muted ltr" dir="ltr">{x.where}</div>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <div className="row">
          <Button variant="primary" icon="download" busy={act.busy} disabled={!chosen.some((p) => !p.complete)} onClick={go} data-testid="cur-go">
            {t('cur.go')}
          </Button>
          <span className="small muted">{chosen.length ? t('cur.sel_total', { n: chosen.length, x: f.bytes(total) }) : t('cur.sel_none')}</span>
        </div>
      </div>
      {ask && <LicenceModal pkgs={ask} onClose={() => setAsk(null)} onOk={() => void submit(true)} busy={act.busy} />}
    </Card>
  )
}

function LicenceModal({ pkgs, onClose, onOk, busy }: { pkgs: CuratedPackage[]; onClose: () => void; onOk: () => void; busy: boolean }) {
  const { t, lang } = useI18n()
  const [yes, setYes] = useState(false)
  return (
    <Modal
      title={t('cur.confirm.title')}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="primary" icon="download" busy={busy} disabled={!yes} onClick={onOk} data-testid="cur-confirm-go">{t('cur.confirm.go')}</Button>
        </>
      }
    >
      <div className="stack">
        <p>{t('cur.confirm.text')}</p>
        <ul className="stack-sm">
          {pkgs.map((p) => (
            <li key={p.id}>
              <span className="strong ltr" dir="ltr">{p.title}</span>
              <div className="small" dir="auto">{p.licence} — {t(('cur.comm.' + p.commercial) as 'cur.comm.yes')}</div>
              {p.licence_url && <a className="small" href={p.licence_url} target="_blank" rel="noreferrer noopener">{t('cur.licence_link')}</a>}
              <div className="small muted" dir="auto">{(lang === 'en' ? p.note.en : p.note.fa) || ''}</div>
            </li>
          ))}
        </ul>
        <CheckField label={t('cur.confirm.check')} checked={yes} onChange={setYes} />
      </div>
    </Modal>
  )
}
