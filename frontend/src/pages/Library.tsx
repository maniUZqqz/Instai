import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { DevTemplate, StepKind, StylePreset, TemplateStep, ThemePreset } from '../api/types'
import { useConfirm, useToast } from '../components/feedback'
import { PaletteEditor } from '../components/PaletteEditor'
import { StyleDetails, Swatch } from '../components/StylePicker'
import { AreaField, Badge, Button, Card, CheckField, ErrorState, ExtLink, Loading, Notice, NumberField, PageHead, SelectField, Tabs, TextField } from '../components/ui'
import { useAction, useHashTab, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { desc, invalidateLibrary, nm, useLibrary, useTemplates, vocab } from '../library'

const TABS = ['styles', 'themes', 'templates'] as const
type Tab = (typeof TABS)[number]

export default function LibraryPage() {
  const { t } = useI18n()
  useTitle(t('lib.title'))
  const [tab, setTab] = useHashTab(TABS, 'styles')
  return (
    <div className="stack">
      <PageHead title={t('lib.title')} crumbs={[{ label: t('lib.title') }]} />
      <p className="muted">{t('lib.intro')}</p>
      <Tabs tabs={TABS.map((k) => ({ key: k, label: t(('lib.tab_' + k) as 'lib.tab_styles') }))} value={tab} onChange={setTab} label={t('lib.tabs')} />
      {tab === 'styles' && <StylesTab />}
      {tab === 'themes' && <ThemesTab />}
      {tab === 'templates' && <TemplatesTab />}
    </div>
  )
}

// ---------------------------------------------------------------- import / export toolbar
function Toolbar({ kind, onNew, extraExport }: { kind: 'style' | 'theme'; onNew: () => void; extraExport?: string }) {
  const { t } = useI18n()
  const toast = useToast()
  const act = useAction()
  const file = useRef<HTMLInputElement>(null)
  const onFile = async (f: File | undefined) => {
    if (!f) return
    let bundle: unknown
    try {
      bundle = JSON.parse(await f.text())
    } catch {
      toast.err(t('lib.import_bad'))
      return
    }
    const r = await act.run(() => api.post<{ imported: { styles: string[]; themes: string[] }; skipped: string[] }>('/library/import', bundle as object))
    if (r) {
      toast.ok(t('lib.imported', { s: r.imported.styles.length, t: r.imported.themes.length }))
      invalidateLibrary()
    }
    if (file.current) file.current.value = ''
  }
  return (
    <div className="row">
      <Button variant="primary" icon="plus" onClick={onNew}>{kind === 'style' ? t('lib.new_style') : t('lib.new_theme')}</Button>
      <Button icon="upload" busy={act.busy} onClick={() => file.current?.click()}>{t('lib.import')}</Button>
      <input ref={file} type="file" accept="application/json,.json" hidden aria-label={t('lib.import')} onChange={(e) => onFile(e.target.files?.[0])} />
      <ExtLink href={`/api/library/export${extraExport ?? ''}`} download className="btn">{t('lib.export_mine')}</ExtLink>
    </div>
  )
}

// ---------------------------------------------------------------- styles
type StyleDraft = Omit<StylePreset, 'key' | 'kind' | 'builtin' | 'based_on' | 'origin' | 'thumbnail_url'> & { key?: string }
const blankStyle = (): StyleDraft => ({
  name_fa: '', name_en: '', description_fa: '', description_en: '', realism: 'anime', family: 'anime', animation: 'limited_2d', fps_feel: 12, image_positive: '', image_negative: '',
  video_positive: '', video_negative: '', palette: ['#EAF2FF', '#3E7BFA', '#FF6F91', '#FFC857', '#243B6B'], lighting: '', mood: '', techniques: ['still_kenburns', 'parallax_25d'],
  sample_prompt: '', theme_key: '', tags: [], thumbnail_asset: null, notes: '',
})

function StylesTab() {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const confirm = useConfirm()
  const act = useAction()
  const [realism, setRealism] = useState('')
  const [q, setQ] = useState('')
  const [sel, setSel] = useState('')
  const [edit, setEdit] = useState<StyleDraft | null>(null)
  const list = useMemo(() => {
    const n = q.trim().toLowerCase()
    return (lib.data?.styles ?? []).filter((s) => (!realism || s.realism === realism) && (!n || [s.name_fa, s.name_en, s.description_en, ...s.tags].join(' ').toLowerCase().includes(n)))
  }, [lib.data, realism, q])
  if (lib.error) return <ErrorState error={lib.error} onRetry={lib.reload} />
  if (!lib.data) return <Loading />
  const cur = lib.data.styles.find((s) => s.key === sel)
  const duplicate = async (s: StylePreset) => {
    const r = await act.run(() => api.post<StylePreset>(`/library/style/${s.key}/duplicate`, {}), { success: t('lib.duplicated') })
    if (r) {
      invalidateLibrary()
      setSel(r.key)
    }
  }
  const remove = async (s: StylePreset) => {
    if (!(await confirm({ message: t('lib.delete_confirm', { name: nm(s, lang) }), danger: true, confirmLabel: t('common.delete') }))) return
    await act.run(async () => { await api.del(`/library/style/${s.key}`); setSel(''); invalidateLibrary() }, { success: t('common.deleted') })
  }
  return (
    <div className="stack">
      <Toolbar kind="style" onNew={() => setEdit(blankStyle())} />
      {edit && (
        <StyleEditor
          draft={edit}
          onClose={() => setEdit(null)}
          onSaved={(k) => { setEdit(null); setSel(k); invalidateLibrary() }}
        />
      )}
      <div className="filter-chips" role="group" aria-label={t('lib.realism')}>
        <button type="button" className={'filter-chip' + (realism === '' ? ' on' : '')} aria-pressed={realism === ''} onClick={() => setRealism('')}>{t('lib.all')} ({lib.data.styles.length})</button>
        {lib.data.realism.map((r) => (
          <button key={r.key} type="button" className={'filter-chip' + (realism === r.key ? ' on' : '')} aria-pressed={realism === r.key} onClick={() => setRealism(r.key)}>
            {lang === 'fa' ? r.fa : r.en} ({lib.data!.styles.filter((s) => s.realism === r.key).length})
          </button>
        ))}
      </div>
      <div className="field">
        <label htmlFor="lib-q" className="sr-only">{t('lib.search')}</label>
        <input id="lib-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('lib.search')} />
      </div>
      <div className="choice-grid style-grid">
        {list.map((s) => (
          <button key={s.key} type="button" className={'choice style-card as-button' + (sel === s.key ? ' selected' : '')} aria-pressed={sel === s.key} onClick={() => setSel(sel === s.key ? '' : s.key)}>
            <Swatch palette={s.palette} url={s.thumbnail_url} />
            <span className="strong">{nm(s, lang)}</span>
            <span className="small muted">{vocab(lib.data!.animations, s.animation, lang)}</span>
            {!s.builtin && <Badge tone="info">{t('lib.mine')}</Badge>}
          </button>
        ))}
        {list.length === 0 && <p className="muted">{t('lib.none_found')}</p>}
      </div>
      {cur && (
        <div className="stack">
          <StyleDetails style={cur} />
          <div className="row">
            <Button icon="copy" busy={act.busy} onClick={() => duplicate(cur)}>{t('lib.duplicate')}</Button>
            {!cur.builtin && <Button icon="edit" onClick={() => setEdit({ ...cur })}>{t('common.edit')}</Button>}
            <ExtLink href={`/api/library/export?styles=${cur.key}`} download className="btn">{t('lib.export_one')}</ExtLink>
            {!cur.builtin && <Button variant="danger" icon="trash" onClick={() => remove(cur)}>{t('common.delete')}</Button>}
          </div>
          {cur.builtin && <p className="small muted">{t('lib.builtin_note')}</p>}
          {!cur.builtin && <ThumbnailUpload style={cur} />}
        </div>
      )}
    </div>
  )
}

function ThumbnailUpload({ style }: { style: StylePreset }) {
  const { t } = useI18n()
  const act = useAction()
  const file = useRef<HTMLInputElement>(null)
  const onFile = async (f: File | undefined) => {
    if (!f) return
    const data = await new Promise<string>((res, rej) => {
      const r = new FileReader()
      r.onload = () => res(String(r.result))
      r.onerror = () => rej(r.error)
      r.readAsDataURL(f)
    })
    const ok = await act.run(async () => { await api.post(`/library/style/${style.key}/thumbnail`, { data }); invalidateLibrary(); return true }, { success: t('common.saved') })
    if (ok && file.current) file.current.value = ''
  }
  return (
    <div className="row">
      <Button icon="upload" busy={act.busy} onClick={() => file.current?.click()}>{t('lib.thumb_upload')}</Button>
      <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label={t('lib.thumb_upload')} onChange={(e) => onFile(e.target.files?.[0])} />
      <span className="small muted">{t('lib.thumb_hint')}</span>
    </div>
  )
}

function StyleEditor({ draft, onClose, onSaved }: { draft: StyleDraft; onClose: () => void; onSaved: (key: string) => void }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const act = useAction()
  const [d, setD] = useState<StyleDraft>(draft)
  const set = (p: Partial<StyleDraft>) => setD((x) => ({ ...x, ...p }))
  const isNew = !draft.key
  const valid = (d.name_fa.trim() || d.name_en.trim()) && d.image_positive.trim()
  const save = async () => {
    const body = { ...d, tags: d.tags }
    const r = await act.run(() => (isNew ? api.post<StylePreset>('/library/style', body) : api.patch<StylePreset>(`/library/style/${draft.key}`, body)), { success: t('common.saved') })
    if (r) onSaved(r.key)
  }
  const L = lib.data
  return (
    <Card title={isNew ? t('lib.new_style') : t('lib.edit_style')} actions={<Button size="sm" variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>}>
      <div className="stack">
        <div className="grid-2">
          <TextField label={t('lib.name_fa')} value={d.name_fa} onChange={(v) => set({ name_fa: v })} required={!d.name_en} />
          <TextField label={t('lib.name_en')} ltr value={d.name_en} onChange={(v) => set({ name_en: v })} required={!d.name_fa} />
          <AreaField label={t('lib.desc_fa')} compact value={d.description_fa} onChange={(v) => set({ description_fa: v })} />
          <AreaField label={t('lib.desc_en')} compact value={d.description_en} onChange={(v) => set({ description_en: v })} className="ltr" />
        </div>
        <div className="grid-3">
          <SelectField label={t('lib.realism')} value={d.realism} onChange={(v) => set({ realism: v })} options={(L?.realism ?? []).map((r) => ({ value: r.key, label: lang === 'fa' ? r.fa : r.en }))} />
          <SelectField label={t('lib.family')} value={d.family} onChange={(v) => set({ family: v })} options={(L?.families ?? []).map((r) => ({ value: r.key, label: lang === 'fa' ? r.fa : r.en }))} />
          <SelectField label={t('lib.animation')} value={d.animation} onChange={(v) => set({ animation: v })} options={(L?.animations ?? []).map((r) => ({ value: r.key, label: lang === 'fa' ? r.fa : r.en }))} />
          <NumberField label={t('lib.fps')} min={4} max={60} value={d.fps_feel} onChange={(v) => set({ fps_feel: v ?? 12 })} hint={t('lib.fps_hint')} />
          <SelectField label={t('lib.default_theme')} value={d.theme_key} onChange={(v) => set({ theme_key: v })} options={[{ value: '', label: '—' }, ...(L?.themes ?? []).map((th) => ({ value: th.key, label: nm(th, lang) }))]} />
          <TextField label={t('lib.tags')} ltr value={d.tags.join(', ')} onChange={(v) => set({ tags: v.split(',').map((x) => x.trim()).filter(Boolean) })} />
        </div>
        <AreaField label={t('lib.image_pos')} className="ltr" value={d.image_positive} onChange={(v) => set({ image_positive: v })} required hint={t('lib.image_pos_hint')} />
        <AreaField label={t('lib.image_neg')} className="ltr" compact value={d.image_negative} onChange={(v) => set({ image_negative: v })} />
        <div className="grid-2">
          <AreaField label={t('lib.video_pos')} className="ltr" compact value={d.video_positive} onChange={(v) => set({ video_positive: v })} hint={t('lib.video_pos_hint')} />
          <AreaField label={t('lib.video_neg')} className="ltr" compact value={d.video_negative} onChange={(v) => set({ video_negative: v })} />
        </div>
        <PaletteEditor label={t('lib.palette')} value={d.palette} onChange={(v) => set({ palette: v })} />
        <div className="grid-2">
          <TextField label={t('lib.lighting')} ltr value={d.lighting} onChange={(v) => set({ lighting: v })} />
          <TextField label={t('lib.mood')} value={d.mood} onChange={(v) => set({ mood: v })} />
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field-label">{t('lib.techniques')}</legend>
          <div className="row">
            {(L?.techniques ?? []).map((x) => (
              <CheckField key={x} label={t(('tech.' + x) as 'tech.still_kenburns')} checked={d.techniques.includes(x)} onChange={(on) => set({ techniques: on ? [...d.techniques, x] : d.techniques.filter((y) => y !== x) })} />
            ))}
          </div>
        </fieldset>
        <AreaField label={t('lib.sample')} className="ltr" compact value={d.sample_prompt} onChange={(v) => set({ sample_prompt: v })} />
        <Notice tone="info">{t('lib.no_names_note')}</Notice>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!valid} onClick={save}>{t('common.save')}</Button>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- themes
type ThemeDraft = Omit<ThemePreset, 'key' | 'kind' | 'builtin' | 'based_on' | 'origin'> & { key?: string }
const blankTheme = (): ThemeDraft => ({
  name_fa: '', name_en: '', description_fa: '', description_en: '', palette: ['#FFF7FB', '#F7A8C4', '#A8E6CF', '#C3B1E1', '#8C7AA9', '#FFFFFF'], lighting: '', mood: '', prompt_fragment: '',
  negative_fragment: '', tags: [], notes: '',
  typography: { title_weight: 'bold', title_case: 'normal', title_animation: 'fade', subtitle_color: '#FFFFFF', subtitle_outline: '#000000', subtitle_position: 'bottom', subtitle_box_opacity: 0, subtitle_size: 64 },
})

function ThemesTab() {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const confirm = useConfirm()
  const act = useAction()
  const [sel, setSel] = useState('')
  const [edit, setEdit] = useState<ThemeDraft | null>(null)
  if (lib.error) return <ErrorState error={lib.error} onRetry={lib.reload} />
  if (!lib.data) return <Loading />
  const cur = lib.data.themes.find((x) => x.key === sel)
  return (
    <div className="stack">
      <Toolbar kind="theme" onNew={() => setEdit(blankTheme())} />
      {edit && <ThemeEditor draft={edit} onClose={() => setEdit(null)} onSaved={(k) => { setEdit(null); setSel(k); invalidateLibrary() }} />}
      <div className="choice-grid theme-grid">
        {lib.data.themes.map((th) => (
          <button key={th.key} type="button" className={'choice theme-card as-button' + (sel === th.key ? ' selected' : '')} aria-pressed={sel === th.key} onClick={() => setSel(sel === th.key ? '' : th.key)}>
            <Swatch palette={th.palette} height={40} />
            <span className="strong small">{nm(th, lang)}</span>
            <span className="small muted">{th.mood}</span>
            {!th.builtin && <Badge tone="info">{t('lib.mine')}</Badge>}
          </button>
        ))}
      </div>
      {cur && (
        <div className="card soft flat stack-sm">
          <div className="row between"><h3>{nm(cur, lang)}</h3>{cur.builtin ? <Badge>{t('lib.builtin')}</Badge> : <Badge tone="info">{t('lib.mine')}</Badge>}</div>
          <p>{desc(cur, lang)}</p>
          <div className="row">{cur.palette.map((c, i) => <span key={i} className="chip-color"><i style={{ background: c }} /> <span className="ltr small">{c}</span></span>)}</div>
          <dl className="kv small">
            <dt>{t('lib.lighting')}</dt><dd>{cur.lighting}</dd>
            <dt>{t('lib.mood')}</dt><dd>{cur.mood}</dd>
            <dt>{t('lib.typography')}</dt>
            <dd className="row">
              <Badge>{t('lib.title_weight')}: {cur.typography.title_weight}</Badge>
              <Badge>{t('lib.title_anim')}: {cur.typography.title_animation}</Badge>
              <Badge>{t('lib.sub_pos')}: {cur.typography.subtitle_position}</Badge>
              <span className="chip-color"><i style={{ background: cur.typography.subtitle_color }} /> <i style={{ background: cur.typography.subtitle_outline }} /></span>
            </dd>
            <dt>{t('lib.prompt_fragment')}</dt><dd className="ltr">{cur.prompt_fragment}</dd>
          </dl>
          <div className="row">
            <Button icon="copy" busy={act.busy} onClick={async () => { const r = await act.run(() => api.post<ThemePreset>(`/library/theme/${cur.key}/duplicate`, {}), { success: t('lib.duplicated') }); if (r) { invalidateLibrary(); setSel(r.key) } }}>{t('lib.duplicate')}</Button>
            {!cur.builtin && <Button icon="edit" onClick={() => setEdit({ ...cur })}>{t('common.edit')}</Button>}
            <ExtLink href={`/api/library/export?themes=${cur.key}`} download className="btn">{t('lib.export_one')}</ExtLink>
            {!cur.builtin && <Button variant="danger" icon="trash" onClick={async () => { if (await confirm({ message: t('lib.delete_confirm', { name: nm(cur, lang) }), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/library/theme/${cur.key}`); setSel(''); invalidateLibrary() }, { success: t('common.deleted') }) }}>{t('common.delete')}</Button>}
          </div>
        </div>
      )}
    </div>
  )
}

function ThemeEditor({ draft, onClose, onSaved }: { draft: ThemeDraft; onClose: () => void; onSaved: (key: string) => void }) {
  const { t } = useI18n()
  const lib = useLibrary()
  const act = useAction()
  const [d, setD] = useState<ThemeDraft>(draft)
  const set = (p: Partial<ThemeDraft>) => setD((x) => ({ ...x, ...p }))
  const ty = d.typography
  const setTy = (p: Partial<typeof ty>) => setD((x) => ({ ...x, typography: { ...x.typography, ...p } }))
  const isNew = !draft.key
  const V = lib.data?.typography
  const save = async () => {
    const r = await act.run(() => (isNew ? api.post<ThemePreset>('/library/theme', d) : api.patch<ThemePreset>(`/library/theme/${draft.key}`, d)), { success: t('common.saved') })
    if (r) onSaved(r.key)
  }
  const opt = (xs: string[] | undefined) => (xs ?? []).map((x) => ({ value: x, label: x }))
  return (
    <Card title={isNew ? t('lib.new_theme') : t('lib.edit_theme')} actions={<Button size="sm" variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>}>
      <div className="stack">
        <div className="grid-2">
          <TextField label={t('lib.name_fa')} value={d.name_fa} onChange={(v) => set({ name_fa: v })} required={!d.name_en} />
          <TextField label={t('lib.name_en')} ltr value={d.name_en} onChange={(v) => set({ name_en: v })} required={!d.name_fa} />
          <AreaField label={t('lib.desc_fa')} compact value={d.description_fa} onChange={(v) => set({ description_fa: v })} />
          <AreaField label={t('lib.desc_en')} compact className="ltr" value={d.description_en} onChange={(v) => set({ description_en: v })} />
        </div>
        <PaletteEditor label={t('lib.palette')} value={d.palette} onChange={(v) => set({ palette: v })} max={6} roles={lib.data?.palette_roles} />
        <div className="grid-2">
          <TextField label={t('lib.lighting')} ltr value={d.lighting} onChange={(v) => set({ lighting: v })} />
          <TextField label={t('lib.mood')} value={d.mood} onChange={(v) => set({ mood: v })} />
        </div>
        <AreaField label={t('lib.prompt_fragment')} className="ltr" compact value={d.prompt_fragment} onChange={(v) => set({ prompt_fragment: v })} />
        <AreaField label={t('lib.negative_fragment')} className="ltr" compact value={d.negative_fragment} onChange={(v) => set({ negative_fragment: v })} />
        <fieldset className="card soft flat" style={{ margin: 0 }}>
          <legend className="strong">{t('lib.typography')}</legend>
          <div className="grid-3">
            <SelectField label={t('lib.title_weight')} value={ty.title_weight} onChange={(v) => setTy({ title_weight: v })} options={opt(V?.title_weights)} />
            <SelectField label={t('lib.title_case')} value={ty.title_case} onChange={(v) => setTy({ title_case: v })} options={opt(V?.title_cases)} />
            <SelectField label={t('lib.title_anim')} value={ty.title_animation} onChange={(v) => setTy({ title_animation: v })} options={opt(V?.title_animations)} />
            <SelectField label={t('lib.sub_pos')} value={ty.subtitle_position} onChange={(v) => setTy({ subtitle_position: v })} options={opt(V?.subtitle_positions)} />
            <NumberField label={t('pf.sub_size')} min={24} max={120} value={ty.subtitle_size} onChange={(v) => setTy({ subtitle_size: v ?? 64 })} />
            <NumberField label={t('lib.sub_box')} min={0} max={1} step={0.05} value={ty.subtitle_box_opacity} onChange={(v) => setTy({ subtitle_box_opacity: v ?? 0 })} />
            <div className="field"><label htmlFor="th-sc">{t('pf.sub_color')}</label><input id="th-sc" type="color" value={ty.subtitle_color} onChange={(e) => setTy({ subtitle_color: e.target.value.toUpperCase() })} /></div>
            <div className="field"><label htmlFor="th-so">{t('pf.sub_outline')}</label><input id="th-so" type="color" value={ty.subtitle_outline} onChange={(e) => setTy({ subtitle_outline: e.target.value.toUpperCase() })} /></div>
          </div>
        </fieldset>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!(d.name_fa.trim() || d.name_en.trim())} onClick={save}>{t('common.save')}</Button>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- development templates
const FIXED_KINDS: StepKind[] = ['bible', 'composition', 'gate']

function TemplatesTab() {
  const { t, lang } = useI18n()
  const tpl = useTemplates()
  const confirm = useConfirm()
  const act = useAction()
  const [edit, setEdit] = useState<DevTemplate | null>(null)
  if (tpl.error) return <ErrorState error={tpl.error} onRetry={tpl.reload} />
  if (!tpl.data) return <Loading />
  return (
    <div className="stack">
      <p className="muted">{t('tpl.intro')}</p>
      <div className="row">
        <Button variant="primary" icon="plus" onClick={() => setEdit({ key: '', base_format: 'custom', builtin: false, needs_source: false, name_fa: '', name_en: '', description_fa: '', description_en: '', default_series: { episodes: 5, episode_length_sec: 45 }, steps: [] })}>{t('tpl.new')}</Button>
      </div>
      {edit && <TemplateEditor draft={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); invalidateLibrary() }} />}
      <div className="grid-auto">
        {tpl.data.templates.map((x) => (
          <Card key={x.key} title={nm(x, lang)} actions={x.builtin ? <Badge>{t('lib.builtin')}</Badge> : <Badge tone="info">{t('lib.mine')}</Badge>}>
            <div className="stack-sm">
              <p className="small muted">{desc(x, lang)}</p>
              <ol className="small steps-list">
                {x.steps.map((s) => (
                  <li key={s.key}><Badge>{t(('tpl.kind_' + s.kind) as 'tpl.kind_source')}</Badge> {lang === 'fa' ? s.title_fa : s.title_en}</li>
                ))}
              </ol>
              <div className="row">
                <Button size="sm" icon="copy" busy={act.busy} onClick={async () => { const r = await act.run(() => api.post<DevTemplate>(`/templates/${x.key}/duplicate`, {}), { success: t('lib.duplicated') }); if (r) { invalidateLibrary(); setEdit(r) } }}>{t('lib.duplicate')}</Button>
                {!x.builtin && <Button size="sm" icon="edit" onClick={() => setEdit(x)}>{t('common.edit')}</Button>}
                {!x.builtin && <Button size="sm" variant="danger" icon="trash" onClick={async () => { if (await confirm({ message: t('lib.delete_confirm', { name: nm(x, lang) }), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/templates/${x.key}`); invalidateLibrary() }, { success: t('common.deleted') }) }}>{t('common.delete')}</Button>}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

function TemplateEditor({ draft, onClose, onSaved }: { draft: DevTemplate; onClose: () => void; onSaved: () => void }) {
  const { t, lang } = useI18n()
  const tpl = useTemplates()
  const act = useAction()
  const [d, setD] = useState<DevTemplate>({ ...draft, steps: draft.steps.filter((s) => !FIXED_KINDS.includes(s.kind)) })
  const set = (p: Partial<DevTemplate>) => setD((x) => ({ ...x, ...p }))
  const setStep = (i: number, p: Partial<TemplateStep>) => set({ steps: d.steps.map((s, j) => (j === i ? { ...s, ...p, params: { ...s.params, ...(p.params ?? {}) } } : s)) })
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= d.steps.length) return
    const steps = d.steps.slice()
    ;[steps[i], steps[j]] = [steps[j], steps[i]]
    set({ steps })
  }
  const [kind, setKind] = useState<StepKind>('brainstorm')
  const addStep = () => set({ steps: [...d.steps, { key: '', kind, title_fa: '', title_en: '', help_fa: '', help_en: '', params: kind === 'brainstorm' ? { lens: 'series_concept', count: 6 } : kind === 'research' ? { mode: 'topic' } : {} }] })
  const isNew = !draft.key
  const save = async () => {
    const r = await act.run(() => (isNew ? api.post<DevTemplate>('/templates', d) : api.patch<DevTemplate>(`/templates/${draft.key}`, d)), { success: t('common.saved') })
    if (r) onSaved()
  }
  const kinds = (tpl.data?.step_kinds ?? []).filter((k) => !FIXED_KINDS.includes(k))
  return (
    <Card title={isNew ? t('tpl.new') : t('tpl.edit')} actions={<Button size="sm" variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>}>
      <div className="stack">
        <div className="grid-2">
          <TextField label={t('lib.name_fa')} value={d.name_fa} onChange={(v) => set({ name_fa: v })} />
          <TextField label={t('lib.name_en')} ltr value={d.name_en} onChange={(v) => set({ name_en: v })} />
          <AreaField label={t('lib.desc_fa')} compact value={d.description_fa} onChange={(v) => set({ description_fa: v })} />
          <AreaField label={t('lib.desc_en')} compact className="ltr" value={d.description_en} onChange={(v) => set({ description_en: v })} />
          <SelectField label={t('tpl.base_format')} value={d.base_format} onChange={(v) => set({ base_format: v })} options={(tpl.data?.formats ?? []).map((f) => ({ value: f, label: t(('tpl.format_' + f) as 'tpl.format_custom') }))} hint={t('tpl.base_format_hint')} />
          <div className="grid-2">
            <NumberField label={t('wiz.episodes')} min={1} max={60} value={d.default_series.episodes} onChange={(v) => set({ default_series: { ...d.default_series, episodes: v ?? 5 } })} />
            <NumberField label={t('wiz.length')} min={10} max={180} value={d.default_series.episode_length_sec} onChange={(v) => set({ default_series: { ...d.default_series, episode_length_sec: v ?? 45 } })} />
          </div>
        </div>
        <h3>{t('tpl.steps')}</h3>
        {d.steps.length === 0 && <p className="muted">{t('tpl.no_steps')}</p>}
        <ol className="stack steps-edit">
          {d.steps.map((s, i) => (
            <li key={i} className="card soft flat stack-sm">
              <div className="row between">
                <span className="strong">{i + 1}. {t(('tpl.kind_' + s.kind) as 'tpl.kind_source')}</span>
                <span className="row">
                  <Button size="sm" variant="ghost" iconOnly icon="up" aria-label={t('tpl.move_up')} disabled={i === 0} onClick={() => move(i, -1)} />
                  <Button size="sm" variant="ghost" iconOnly icon="down" aria-label={t('tpl.move_down')} disabled={i === d.steps.length - 1} onClick={() => move(i, 1)} />
                  <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => set({ steps: d.steps.filter((_, j) => j !== i) })} />
                </span>
              </div>
              <div className="grid-2">
                <TextField label={t('tpl.step_title_fa')} value={s.title_fa} onChange={(v) => setStep(i, { title_fa: v })} />
                <TextField label={t('tpl.step_title_en')} ltr value={s.title_en} onChange={(v) => setStep(i, { title_en: v })} />
                <TextField label={t('tpl.step_help_fa')} value={s.help_fa} onChange={(v) => setStep(i, { help_fa: v })} />
                <TextField label={t('tpl.step_help_en')} ltr value={s.help_en} onChange={(v) => setStep(i, { help_en: v })} />
              </div>
              {s.kind === 'brainstorm' && (
                <div className="grid-3">
                  <SelectField label={t('tpl.lens')} value={s.params.lens ?? 'series_concept'} onChange={(v) => setStep(i, { params: { lens: v } })} options={(tpl.data?.lenses ?? []).map((l) => ({ value: l.key, label: lang === 'fa' ? l.fa : l.en }))} />
                  <TextField label={t('tpl.board')} ltr value={s.params.board ?? ''} onChange={(v) => setStep(i, { params: { board: v } })} hint={t('tpl.board_hint')} />
                  <NumberField label={t('tpl.count')} min={2} max={12} value={s.params.count ?? 6} onChange={(v) => setStep(i, { params: { count: v ?? 6 } })} />
                </div>
              )}
              {s.kind === 'research' && (
                <SelectField label={t('tpl.mode')} value={s.params.mode ?? 'topic'} onChange={(v) => setStep(i, { params: { mode: v } })} options={[{ value: 'canon', label: t('tpl.mode_canon') }, { value: 'topic', label: t('tpl.mode_topic') }]} />
              )}
            </li>
          ))}
        </ol>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <SelectField label={t('tpl.add_kind')} value={kind} onChange={(v) => setKind(v as StepKind)} options={kinds.map((k) => ({ value: k, label: t(('tpl.kind_' + k) as 'tpl.kind_source') }))} />
          <Button icon="plus" onClick={addStep}>{t('tpl.add_step')}</Button>
        </div>
        <Notice tone="info">{t('tpl.fixed_note')}</Notice>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!(d.name_fa.trim() || d.name_en.trim())} onClick={save}>{t('common.save')}</Button>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
        </div>
      </div>
    </Card>
  )
}
