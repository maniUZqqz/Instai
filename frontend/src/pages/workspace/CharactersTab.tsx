import { useState } from 'react'
import { api } from '../../api/client'
import type { Character } from '../../api/types'
import { CharacterFields, emptyChar, type CharDraft } from '../../components/CharacterFields'
import { useConfirm } from '../../components/feedback'
import { Badge, Button, Card, CheckField, Empty, Notice, SelectField, TextField, AreaField } from '../../components/ui'
import { useAction } from '../../hooks'
import { useI18n } from '../../i18n'
import { useWs } from './Workspace'

const REF_KINDS = ['sheet', 'image', 'pose', 'expression', 'lora', 'voice']

export function CharactersTab() {
  const { t } = useI18n()
  const { page, reload } = useWs()
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState<CharDraft>(emptyChar())
  const act = useAction()
  const add = async () => {
    const c = await act.run(() => api.post<Character>(`/pages/${page.id}/characters`, { ...draft, name: draft.name.trim() }), { success: t('chars.added') })
    if (c) {
      setDraft(emptyChar())
      setAdding(false)
      reload()
    }
  }
  return (
    <div className="stack">
      <div className="row between">
        <h2>{t('ws.tab_characters')}</h2>
        <Button variant="primary" icon="plus" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
          {t('wiz.add_char')}
        </Button>
      </div>
      <p className="muted">{t('chars.intro')}</p>
      {adding && (
        <Card title={t('wiz.add_char')}>
          <CharacterFields value={draft} onChange={setDraft} extended />
          <div className="row" style={{ marginBlockStart: '1rem' }}>
            <Button variant="primary" icon="check" busy={act.busy} disabled={!draft.name.trim()} onClick={add}>
              {t('common.add')}
            </Button>
            <Button onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
          </div>
        </Card>
      )}
      {page.characters.length === 0 && !adding ? (
        <Empty icon="users" title={t('chars.empty_title')} text={t('chars.empty_text')} action={<Button variant="primary" icon="plus" onClick={() => setAdding(true)}>{t('wiz.add_char')}</Button>} />
      ) : (
        <div className="stack">
          {page.characters.map((c) => (
            <CharacterCard key={c.id} c={c} onChanged={reload} />
          ))}
        </div>
      )}
    </div>
  )
}

function toDraft(c: Character): CharDraft {
  return { name: c.name, role: c.role, personality: c.personality, appearance: c.appearance, abilities: c.abilities, motivations: c.motivations, profile: c.profile, is_original: c.is_original, franchise: c.franchise, voice: c.voice ?? {} }
}

function CharacterCard({ c, onChanged }: { c: Character; onChanged: () => void }) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<CharDraft>(() => toDraft(c))
  const act = useAction()
  const patch = (body: Record<string, unknown>, success?: string) => act.run(async () => { await api.patch(`/characters/${c.id}`, body); onChanged() }, { success })
  const remove = async () => {
    if (!(await confirm({ message: t('chars.delete_confirm', { name: c.name }), danger: true, confirmLabel: t('common.delete') }))) return
    await act.run(async () => { await api.del(`/characters/${c.id}`); onChanged() }, { success: t('chars.deleted') })
  }
  return (
    <Card
      title={
        <span className="row">
          {c.name}
          {c.role && <span className="muted small">· {c.role}</span>}
        </span>
      }
      actions={
        <>
          {c.approved ? <Badge tone="ok">{t('chars.approved')}</Badge> : <Badge>{t('chars.not_approved')}</Badge>}
          {!c.is_original && <Badge tone="warn">{c.franchise ? t('chars.fan_of', { name: c.franchise }) : t('chars.fan')}</Badge>}
          <Button size="sm" icon={open ? 'up' : 'edit'} onClick={() => { setDraft(toDraft(c)); setOpen((o) => !o) }} aria-expanded={open}>
            {open ? t('common.close') : t('common.edit')}
          </Button>
        </>
      }
    >
      {!open && (
        <div className="stack-sm">
          {c.personality && <p>{c.personality}</p>}
          {c.appearance && <p className="muted small">{c.appearance}</p>}
          <div className="row small muted">
            {c.voice?.engine && <span>{t('char.voice_engine')}: {c.voice.engine}</span>}
            <span>{t('chars.refs_n', { n: c.references.length })}</span>
          </div>
        </div>
      )}
      {open && (
        <div className="stack">
          <CharacterFields value={draft} onChange={setDraft} extended />
          <div className="row">
            <Button variant="primary" icon="save" busy={act.busy} disabled={!draft.name.trim()} onClick={async () => { await patch({ ...draft, name: draft.name.trim() }, t('common.saved')); setOpen(false) }}>
              {t('common.save')}
            </Button>
            <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button variant="danger" icon="trash" onClick={remove}>{t('common.delete')}</Button>
          </div>
          <hr className="divider" />
          <CheckField label={t('chars.approve')} hint={t('chars.approve_hint')} checked={c.approved} onChange={(v) => patch({ approved: v })} />
          <References c={c} onChanged={onChanged} />
        </div>
      )}
      {!open && (
        <div className="row" style={{ marginBlockStart: '0.75rem' }}>
          <Button size="sm" variant="ghost" icon="check" onClick={() => patch({ approved: !c.approved })}>
            {c.approved ? t('chars.unapprove') : t('chars.approve')}
          </Button>
          <Button size="sm" variant="ghost" icon="trash" onClick={remove}>{t('common.delete')}</Button>
        </div>
      )}
    </Card>
  )
}

function References({ c, onChanged }: { c: Character; onChanged: () => void }) {
  const { t, tr } = useI18n()
  const confirm = useConfirm()
  const [kind, setKind] = useState('sheet')
  const [label, setLabel] = useState('')
  const [notes, setNotes] = useState('')
  const act = useAction()
  const add = async () => {
    const r = await act.run(async () => { await api.post(`/characters/${c.id}/references`, { kind, label: label.trim(), notes }); onChanged(); return true }, { success: t('chars.ref_added') })
    if (r) { setLabel(''); setNotes('') }
  }
  return (
    <section className="stack" aria-label={t('chars.refs')}>
      <h3>{t('chars.refs')}</h3>
      <Notice tone="info">{t('chars.refs_note')}</Notice>
      {c.references.length === 0 && <p className="muted">{t('chars.refs_empty')}</p>}
      {c.references.map((r) => (
        <div key={r.id} className="card soft flat row between" style={{ flexWrap: 'wrap' }}>
          <div className="grow">
            <div className="row">
              <Badge>{tr('refkind.' + r.kind, r.kind)}</Badge>
              <span className="strong">{r.label || '—'}</span>
              {r.asset_url && <a href={r.asset_url} target="_blank" rel="noreferrer noopener">{t('common.open')}</a>}
            </div>
            {r.notes && <div className="small muted">{r.notes}</div>}
          </div>
          <CheckField label={t('chars.approved')} checked={r.approved} onChange={(v) => act.run(async () => { await api.patch(`/references/${r.id}`, { approved: v }); onChanged() })} />
          <Button
            size="sm"
            variant="ghost"
            iconOnly
            icon="trash"
            aria-label={t('common.delete')}
            onClick={async () => {
              if (await confirm({ message: t('chars.ref_delete_confirm'), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/references/${r.id}`); onChanged() })
            }}
          />
        </div>
      ))}
      <div className="grid-3">
        <SelectField label={t('chars.ref_kind')} value={kind} onChange={setKind} options={REF_KINDS.map((k) => ({ value: k, label: tr('refkind.' + k, k) }))} />
        <TextField label={t('chars.ref_label')} value={label} onChange={setLabel} />
        <AreaField label={t('chars.ref_notes')} value={notes} onChange={setNotes} compact />
      </div>
      <div>
        <Button icon="plus" busy={act.busy} onClick={add}>{t('chars.ref_add')}</Button>
      </div>
    </section>
  )
}
