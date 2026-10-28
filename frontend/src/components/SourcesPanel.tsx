import { useState } from 'react'
import { api } from '../api/client'
import type { Source } from '../api/types'
import { useAction, useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { useConfirm } from './feedback'
import { Async, AreaField, Badge, Button, Card, CardSkeletons, Empty, ExtLink, Notice, SelectField, TextField } from './ui'

const STANCES = ['established', 'contested', 'speculative']

/** Sources of a page (explainers). Sources the owner adds are never marked "verified": only the system's own fetches are. */
export function SourcesPanel({ pageId, seriesId, episodeId, onChanged }: { pageId: number; seriesId?: number; episodeId?: number; onChanged?: () => void }) {
  const { t, tr } = useI18n()
  const confirm = useConfirm()
  const q = useQuery<Source[]>(`/pages/${pageId}/sources`)
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const blank = { title: '', url: '', publisher: '', extract: '', claim: '', stance: 'established' }
  const [draft, setDraft] = useState(blank)
  const act = useAction()
  const changed = () => {
    q.reload()
    onChanged?.()
  }
  const add = async () => {
    const r = await act.run(async () => {
      await api.post(`/pages/${pageId}/sources`, { ...draft, title: draft.title.trim(), series: seriesId ?? null, episode: episodeId ?? null })
      return true
    }, { success: t('src.added') })
    if (r) {
      setDraft(blank)
      setAdding(false)
      changed()
    }
  }
  const saveEdit = async (s: Source, d: typeof blank) => {
    const r = await act.run(async () => {
      await api.patch(`/sources/${s.id}`, d)
      return true
    }, { success: t('common.saved') })
    if (r) {
      setEditId(null)
      changed()
    }
  }
  const remove = async (s: Source) => {
    if (!(await confirm({ message: t('src.delete_confirm', { title: s.title }), danger: true, confirmLabel: t('common.delete') }))) return
    await act.run(async () => {
      await api.del(`/sources/${s.id}`)
      changed()
    }, { success: t('src.deleted') })
  }
  const list = (q.data ?? []).filter((s) => (episodeId ? s.episode === episodeId || s.episode == null : seriesId ? s.series === seriesId || s.series == null : true))
  const form = (d: typeof blank, set: (v: typeof blank) => void) => (
    <div className="stack">
      <TextField label={t('src.title')} required value={d.title} onChange={(v) => set({ ...d, title: v })} />
      <div className="grid-2">
        <TextField label={t('src.url')} type="url" ltr value={d.url} onChange={(v) => set({ ...d, url: v })} placeholder="https://" />
        <TextField label={t('src.publisher')} value={d.publisher} onChange={(v) => set({ ...d, publisher: v })} />
      </div>
      <AreaField label={t('src.claim')} compact value={d.claim} onChange={(v) => set({ ...d, claim: v })} hint={t('src.claim_hint')} />
      <AreaField label={t('src.extract')} compact value={d.extract} onChange={(v) => set({ ...d, extract: v })} hint={t('src.extract_hint')} />
      <SelectField label={t('src.stance')} value={d.stance} onChange={(v) => set({ ...d, stance: v })} options={STANCES.map((k) => ({ value: k, label: tr('stance.' + k, k) }))} />
    </div>
  )
  return (
    <div className="stack">
      <div className="row between">
        <h3>{t('src.title_h')}</h3>
        <Button size="sm" icon="plus" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
          {t('src.add')}
        </Button>
      </div>
      <Notice tone="info">{t('src.note')}</Notice>
      {adding && (
        <Card title={t('src.add')}>
          {form(draft, setDraft)}
          <div className="row" style={{ marginBlockStart: '1rem' }}>
            <Button variant="primary" icon="check" busy={act.busy} disabled={!draft.title.trim()} onClick={add}>
              {t('common.add')}
            </Button>
            <Button onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
          </div>
        </Card>
      )}
      <Async q={q} skeleton={<CardSkeletons n={1} />}>
        {() =>
          list.length === 0 ? (
            <Empty icon="book" title={t('src.empty_title')} text={t('src.empty_text')} />
          ) : (
            <div className="stack">
              {list.map((s) =>
                editId === s.id ? (
                  <EditSource key={s.id} s={s} form={form} onSave={(d) => saveEdit(s, d)} onCancel={() => setEditId(null)} busy={act.busy} />
                ) : (
                  <div key={s.id} className="card soft flat stack-sm">
                    <div className="row between">
                      <span className="strong">{s.title}</span>
                      <span className="row">
                        {s.verified ? <Badge tone="ok">{t('src.verified')}</Badge> : <Badge tone="warn">{t('src.unverified')}</Badge>}
                        <Badge>{tr('stance.' + s.stance, s.stance)}</Badge>
                        <Badge tone="info">{s.added_by === 'user' ? t('src.by_you') : t('src.by_system')}</Badge>
                      </span>
                    </div>
                    {s.publisher && <div className="small muted">{s.publisher}</div>}
                    {s.url && <ExtLink href={s.url} className="ltr small">{s.url}</ExtLink>}
                    {s.claim && <p className="small">{s.claim}</p>}
                    {s.extract && <p className="small muted" style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{s.extract}</p>}
                    <div className="row">
                      <Button size="sm" icon="edit" onClick={() => setEditId(s.id)}>{t('common.edit')}</Button>
                      <Button size="sm" variant="ghost" icon="trash" onClick={() => remove(s)}>{t('common.delete')}</Button>
                    </div>
                  </div>
                ),
              )}
            </div>
          )
        }
      </Async>
    </div>
  )
}

function EditSource({ s, form, onSave, onCancel, busy }: { s: Source; form: (d: any, set: (v: any) => void) => React.ReactNode; onSave: (d: any) => void; onCancel: () => void; busy: boolean }) {
  const { t } = useI18n()
  const [d, setD] = useState({ title: s.title, url: s.url, publisher: s.publisher, extract: s.extract, claim: s.claim, stance: s.stance })
  return (
    <Card title={t('common.edit')}>
      {form(d, setD)}
      <div className="row" style={{ marginBlockStart: '1rem' }}>
        <Button variant="primary" icon="save" busy={busy} disabled={!d.title.trim()} onClick={() => onSave(d)}>{t('common.save')}</Button>
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
      </div>
    </Card>
  )
}
