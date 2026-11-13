import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { BankIdea, IdeasPayload, StartResult } from '../api/ideaTypes'
import type { PageBrief } from '../api/types'
import { useConfirm, useToast } from '../components/feedback'
import { StylePicker, type Look } from '../components/StylePicker'
import { AreaField, Async, Badge, Button, Card, CardSkeletons, CheckField, Empty, Notice, NumberField, PageHead, Segmented, SelectField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import { useI18n, type Lang } from '../i18n'
import { fold, useLibrary } from '../library'
import { TAG_FA, tagLabel } from '../ideaTags'

type Text = 'title' | 'logline' | 'hook' | 'premise'
/** The text of an idea in the interface language (falls back to the other language when one is empty). */
export function ideaText(i: BankIdea, f: Text, lang: Lang): string {
  const fa = i[`${f}_fa` as const]
  const en = i[`${f}_en` as const]
  return (lang === 'fa' ? fa || en : en || fa) || ''
}

function ideaMatches(i: BankIdea, q: string): boolean {
  const words = fold(q).split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const hay = fold([i.title_fa, i.title_en, i.logline_fa, i.logline_en, i.hook_fa, i.hook_en, i.premise_fa, i.premise_en, ...i.tags, ...i.tags.map((x) => TAG_FA[x] ?? ''), i.key.replace(/_/g, ' ')].join(' '))
  return words.every((w) => hay.includes(w))
}

type Source = '' | 'builtin' | 'mine'

export default function IdeasPage() {
  const { t, lang } = useI18n()
  useTitle(t('ideas.title'))
  const [showHidden, setShowHidden] = useState(false)
  const q = useQuery<IdeasPayload>(showHidden ? '/ideas?hidden=1' : '/ideas')
  const [text, setText] = useState('')
  const [category, setCategory] = useState('')
  const [fmt, setFmt] = useState('')
  const [tag, setTag] = useState('')
  const [fav, setFav] = useState(false)
  const [source, setSource] = useState<Source>('')
  const [start, setStart] = useState<string | null>(null)
  const [edit, setEdit] = useState<Partial<BankIdea> | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const toast = useToast()
  const act = useAction()

  const list = useMemo(
    () =>
      (q.data?.ideas ?? []).filter(
        (i) =>
          (!category || i.category === category) &&
          (!fmt || i.format === fmt) &&
          (!tag || i.tags.includes(tag)) &&
          (!fav || i.favorite) &&
          (!source || (source === 'builtin') === i.builtin) &&
          ideaMatches(i, text),
      ),
    [q.data, category, fmt, tag, fav, source, text],
  )
  const surprise = () => {
    if (!list.length) return
    const i = list[Math.floor(Math.random() * list.length)]
    setOpen(i.key)
    window.setTimeout(() => document.getElementById('idea-' + i.key)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 50)
  }
  const mark = async (i: BankIdea, p: { favorite?: boolean; hidden?: boolean }) => {
    const r = await act.run(() => api.post<BankIdea>(`/ideas/${i.key}/mark`, p))
    if (r) q.reload()
  }
  const clearAll = () => {
    setText('')
    setCategory('')
    setFmt('')
    setTag('')
    setFav(false)
    setSource('')
  }
  const filtered = !!(text || category || fmt || tag || fav || source)

  return (
    <div className="stack">
      <PageHead title={t('ideas.title')} crumbs={[{ label: t('ideas.title') }]}>
        <Button variant="primary" icon="plus" onClick={() => setEdit({ category: category || 'mystery', format: 'custom' })}>{t('ideas.new')}</Button>
      </PageHead>
      <p className="muted">{t('ideas.intro')}</p>

      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(d) => (
          <>
            <div className="stack-sm">
              <div className="field">
                <label htmlFor="idea-q" className="sr-only">{t('ideas.search')}</label>
                <input id="idea-q" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('ideas.search')} />
              </div>
              <div className="filter-chips" role="group" aria-label={t('ideas.categories')}>
                <button type="button" className={'filter-chip' + (category === '' ? ' on' : '')} aria-pressed={category === ''} onClick={() => setCategory('')}>
                  {t('lib.all')} <span className="muted">({d.total})</span>
                </button>
                {d.categories.map((c) => (
                  <button key={c.key} type="button" className={'filter-chip' + (category === c.key ? ' on' : '')} aria-pressed={category === c.key} onClick={() => setCategory(category === c.key ? '' : c.key)}>
                    {lang === 'fa' ? c.fa : c.en} <span className="muted">({c.count})</span>
                  </button>
                ))}
              </div>
              <div className="row">
                <Segmented
                  label={t('ideas.source')}
                  value={source}
                  onChange={setSource}
                  options={[
                    { key: '' as Source, label: t('ideas.src_all') },
                    { key: 'builtin' as Source, label: t('ideas.src_builtin') },
                    { key: 'mine' as Source, label: t('ideas.src_mine') },
                  ]}
                />
                <SelectField label={t('ideas.format')} value={fmt} onChange={setFmt} options={[{ value: '', label: t('lib.all') }, ...d.formats.map((f) => ({ value: f.key, label: lang === 'fa' ? f.fa : f.en }))]} />
                <CheckField label={t('ideas.only_fav')} checked={fav} onChange={setFav} />
                <CheckField label={t('ideas.show_hidden')} checked={showHidden} onChange={setShowHidden} />
                {filtered && <Button variant="ghost" onClick={clearAll}>{t('ideas.clear')}</Button>}
                <Button icon="spark" onClick={surprise} disabled={!list.length}>{t('ideas.surprise')}</Button>
              </div>
              <div className="filter-chips" role="group" aria-label={t('ideas.tags')}>
                {d.tags.slice(0, 18).map((x) => (
                  <button key={x.tag} type="button" className={'filter-chip' + (tag === x.tag ? ' on' : '')} aria-pressed={tag === x.tag} onClick={() => setTag(tag === x.tag ? '' : x.tag)}>
                    <span className={lang === 'fa' && TAG_FA[x.tag] ? undefined : 'ltr'}>{tagLabel(x.tag, lang)}</span> <span className="muted">({x.count})</span>
                  </button>
                ))}
              </div>
            </div>

            <GenerateBar categories={d.categories} category={category} onDone={() => q.reload()} />

            {edit && <IdeaEditor draft={edit} categories={d.categories} formats={d.formats} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); q.reload() }} />}

            <p className="small muted" aria-live="polite">{t('ideas.shown', { n: list.length, total: d.total })}</p>
            {list.length === 0 ? (
              <Empty icon="spark" title={t('ideas.none_title')} text={t('ideas.none_text')} action={filtered ? <Button onClick={clearAll}>{t('ideas.clear')}</Button> : undefined} />
            ) : (
              <div className="idea-grid">
                {list.map((i) => (
                  <IdeaCard
                    key={i.key}
                    idea={i}
                    cats={d.categories}
                    open={open === i.key}
                    onToggle={() => setOpen(open === i.key ? null : i.key)}
                    onFav={() => mark(i, { favorite: !i.favorite })}
                    onHide={() => mark(i, { hidden: !i.hidden })}
                    onStart={() => setStart(i.key)}
                    onEdit={() => setEdit({ ...i })}
                    onChanged={() => q.reload()}
                    starting={start === i.key}
                    onCloseStart={() => setStart(null)}
                    onStarted={() => toast.ok(t('ideas.started'))}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </Async>
    </div>
  )
}

function IdeaCard({ idea: i, cats, open, onToggle, onFav, onHide, onStart, onEdit, onChanged, starting, onCloseStart, onStarted }: {
  idea: BankIdea
  cats: IdeasPayload['categories']
  open: boolean
  onToggle: () => void
  onFav: () => void
  onHide: () => void
  onStart: () => void
  onEdit: () => void
  onChanged: () => void
  starting: boolean
  onCloseStart: () => void
  onStarted: () => void
}) {
  const { t, lang } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const cat = cats.find((c) => c.key === i.category)
  const premise = ideaText(i, 'premise', lang)
  const duplicate = async () => {
    const r = await act.run(() => api.post<BankIdea>(`/ideas/${i.key}/duplicate`, {}), { success: t('lib.duplicated') })
    if (r) onChanged()
  }
  const remove = async () => {
    if (!(await confirm({ message: t('lib.delete_confirm', { name: ideaText(i, 'title', lang) }), danger: true, confirmLabel: t('common.delete') }))) return
    await act.run(async () => { await api.del(`/ideas/${i.key}`); onChanged() }, { success: t('common.deleted') })
  }
  return (
    <article id={'idea-' + i.key} className={'card idea-card' + (open || starting ? ' open' : '')}>
      <div className="row between">
        <div className="row">
          {cat && <Badge tone="info">{lang === 'fa' ? cat.fa : cat.en}</Badge>}
          {!i.builtin && <Badge tone="primary">{t('lib.mine')}</Badge>}
          {i.uses > 0 && <Badge tone="ok">{t('ideas.used', { n: i.uses })}</Badge>}
        </div>
        <Button variant="ghost" size="sm" iconOnly icon="star" onClick={onFav} aria-pressed={i.favorite} aria-label={i.favorite ? t('ideas.unfav') : t('ideas.fav')} title={i.favorite ? t('ideas.unfav') : t('ideas.fav')} className={i.favorite ? 'fav-on' : ''} />
      </div>
      <h3>{ideaText(i, 'title', lang)}</h3>
      <p>{ideaText(i, 'logline', lang)}</p>
      <blockquote className="idea-hook"><span className="small muted">{t('ideas.hook')}</span><br />{ideaText(i, 'hook', lang)}</blockquote>
      <div className="row">
        {i.tags.slice(0, 5).map((x) => <Badge key={x}><span className={lang === 'fa' && TAG_FA[x] ? undefined : 'ltr'}>{tagLabel(x, lang)}</span></Badge>)}
      </div>
      {open && premise && <p className="idea-premise">{premise}</p>}
      <div className="row">
        <Button variant="primary" icon="play" onClick={onStart}>{t('ideas.start')}</Button>
        {premise && <Button variant="ghost" onClick={onToggle} aria-expanded={open}>{open ? t('ideas.less') : t('ideas.more')}</Button>}
        <Button variant="ghost" icon="copy" busy={act.busy} onClick={duplicate}>{t('lib.duplicate')}</Button>
        {!i.builtin && <Button variant="ghost" icon="edit" onClick={onEdit}>{t('common.edit')}</Button>}
        {!i.builtin && <Button variant="ghost" icon="trash" onClick={remove}>{t('common.delete')}</Button>}
        {i.builtin && <Button variant="ghost" onClick={onHide}>{i.hidden ? t('ideas.unhide') : t('ideas.hide')}</Button>}
      </div>
      {starting && <StartPanel idea={i} onClose={onCloseStart} onStarted={onStarted} />}
    </article>
  )
}

/** «شروعِ پروژه از این ایده»: pick the page, the language and the look ONCE; a series is made and the development room opens. */
function StartPanel({ idea, onClose, onStarted }: { idea: BankIdea; onClose: () => void; onStarted: () => void }) {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const lib = useLibrary()
  const act = useAction()
  const pages = useQuery<PageBrief[]>('/pages')
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [pageName, setPageName] = useState(ideaText(idea, 'title', lang))
  const [pageId, setPageId] = useState('')
  const [language, setLanguage] = useState<Lang>(lang)
  const [episodes, setEpisodes] = useState<number | null>(idea.episodes)
  const [ownLook, setOwnLook] = useState(true)
  const first = idea.suggested_styles[0]
  const st = lib.style(first ?? '')
  const [look, setLook] = useState<Look>({ style_key: first ?? '', realism: st?.realism ?? '', theme_key: st?.theme_key ?? '' })
  const list = (pages.data ?? []).filter((p) => p.status === 'active')
  const useLook = mode === 'new' || ownLook
  const ready = (mode === 'new' ? pageName.trim() : pageId) && (!useLook || look.style_key)
  const go = async () => {
    const body: Record<string, unknown> = { language, episodes: episodes ?? idea.episodes }
    if (mode === 'new') body.page_name = pageName.trim()
    else body.page_id = Number(pageId)
    if (useLook) {
      body.style_key = look.style_key
      body.theme_key = look.theme_key
    }
    const r = await act.run(() => api.post<StartResult>(`/ideas/${idea.key}/start`, body))
    if (r) {
      onStarted()
      nav(r.series_url)
    }
  }
  return (
    <Card title={t('ideas.start_title')} soft actions={<Button size="sm" variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>}>
      <div className="stack">
        <p className="small muted">{t('ideas.start_intro')}</p>
        <Segmented
          label={t('ideas.start_where')}
          value={mode}
          onChange={setMode}
          options={[
            { key: 'new', label: t('ideas.start_new_page') },
            { key: 'existing', label: t('ideas.start_existing') },
          ]}
        />
        {mode === 'new' ? (
          <TextField label={t('ideas.page_name')} value={pageName} onChange={setPageName} required />
        ) : (
          <>
            <SelectField label={t('ideas.pick_page')} value={pageId} onChange={setPageId} options={[{ value: '', label: '—' }, ...list.map((p) => ({ value: String(p.id), label: p.name }))]} />
            {list.length === 0 && <Notice tone="warn">{t('ideas.no_pages')}</Notice>}
            <CheckField label={t('ideas.own_look')} hint={t('ideas.own_look_hint')} checked={ownLook} onChange={setOwnLook} />
          </>
        )}
        <div className="grid-2">
          <SelectField label={t('ideas.language')} value={language} onChange={(v) => setLanguage(v as Lang)} options={[{ value: 'fa', label: 'فارسی' }, { value: 'en', label: 'English' }]} />
          <NumberField label={t('ideas.episodes')} min={1} max={30} value={episodes} onChange={setEpisodes} />
        </div>
        {useLook && (
          <div className="stack-sm">
            <strong>{t('ideas.pick_look')}</strong>
            <p className="small muted">{t('ideas.pick_look_hint')}</p>
            <StylePicker value={look} onChange={setLook} name={'start-' + idea.key} scroll />
          </div>
        )}
        <div className="row">
          <Button variant="primary" icon="play" busy={act.busy} disabled={!ready} onClick={go}>{t('ideas.start_go')}</Button>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
        </div>
      </div>
    </Card>
  )
}

/** More ideas from the text model (Ollama on this PC). It waits by itself when the model is not running. */
function GenerateBar({ categories, category, onDone }: { categories: IdeasPayload['categories']; category: string; onDone: () => void }) {
  const { t, lang } = useI18n()
  const toast = useToast()
  const [cat, setCat] = useState('')
  const [count, setCount] = useState<number | null>(5)
  const [instruction, setInstruction] = useState('')
  const run = useJobRunner({
    onSucceeded: (j) => {
      toast.ok(t('ideas.gen_done', { n: (j.result?.created as string[] | undefined)?.length ?? 0 }))
      onDone()
    },
  })
  const cats = categories
  const chosen = cat || category || 'mystery'
  return (
    <details className="card soft flat">
      <summary className="strong" style={{ cursor: 'pointer' }}>{t('ideas.gen_title')}</summary>
      <div className="stack" style={{ marginBlockStart: '0.6rem' }}>
        <p className="small muted">{t('ideas.gen_text')}</p>
        <div className="grid-3">
          <SelectField label={t('ideas.gen_category')} value={chosen} onChange={setCat} options={cats.map((c) => ({ value: c.key, label: lang === 'fa' ? c.fa : c.en }))} />
          <NumberField label={t('ideas.gen_count')} min={1} max={8} value={count} onChange={setCount} />
          <TextField label={t('ideas.gen_hint')} value={instruction} onChange={setInstruction} />
        </div>
        <div className="row">
          <Button icon="spark" variant="primary" busy={run.busy} onClick={() => run.start(() => api.post('/ideas/generate', { category: chosen, count: count ?? 5, instruction }))}>{t('ideas.gen_go')}</Button>
          {run.job && !run.succeeded && <span className="small">{run.job.waiting_reason || run.job.progress_text || run.job.status}</span>}
        </div>
        {run.failed && run.job && <Notice tone="warn">{(run.job.error || '').split('\n')[0]}</Notice>}
      </div>
    </details>
  )
}

function IdeaEditor({ draft, categories, formats, onClose, onSaved }: { draft: Partial<BankIdea>; categories: IdeasPayload['categories']; formats: IdeasPayload['formats']; onClose: () => void; onSaved: () => void }) {
  const { t, lang } = useI18n()
  const lib = useLibrary()
  const act = useAction()
  const [d, setD] = useState<Partial<BankIdea>>(draft)
  const set = (p: Partial<BankIdea>) => setD((x) => ({ ...x, ...p }))
  const isNew = !draft.key
  const valid = (d.title_fa?.trim() || d.title_en?.trim()) && (d.logline_fa?.trim() || d.logline_en?.trim())
  const save = async () => {
    const body = { ...d, tags: d.tags ?? [] }
    const r = await act.run(() => (isNew ? api.post<BankIdea>('/ideas', body) : api.patch<BankIdea>(`/ideas/${draft.key}`, body)), { success: t('common.saved') })
    if (r) onSaved()
  }
  const styles = lib.data?.styles ?? []
  return (
    <Card title={isNew ? t('ideas.new') : t('ideas.edit')} actions={<Button size="sm" variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>}>
      <div className="stack">
        <div className="grid-2">
          <TextField label={t('lib.name_fa')} value={d.title_fa ?? ''} onChange={(v) => set({ title_fa: v })} required={!d.title_en} />
          <TextField label={t('lib.name_en')} ltr value={d.title_en ?? ''} onChange={(v) => set({ title_en: v })} required={!d.title_fa} />
          <AreaField label={t('ideas.logline_fa')} compact value={d.logline_fa ?? ''} onChange={(v) => set({ logline_fa: v })} />
          <AreaField label={t('ideas.logline_en')} compact className="ltr" value={d.logline_en ?? ''} onChange={(v) => set({ logline_en: v })} />
          <AreaField label={t('ideas.hook_fa')} compact value={d.hook_fa ?? ''} onChange={(v) => set({ hook_fa: v })} />
          <AreaField label={t('ideas.hook_en')} compact className="ltr" value={d.hook_en ?? ''} onChange={(v) => set({ hook_en: v })} />
          <AreaField label={t('ideas.premise_fa')} compact value={d.premise_fa ?? ''} onChange={(v) => set({ premise_fa: v })} />
          <AreaField label={t('ideas.premise_en')} compact className="ltr" value={d.premise_en ?? ''} onChange={(v) => set({ premise_en: v })} />
        </div>
        <div className="grid-3">
          <SelectField label={t('ideas.category')} value={d.category ?? 'mystery'} onChange={(v) => set({ category: v })} options={categories.map((c) => ({ value: c.key, label: lang === 'fa' ? c.fa : c.en }))} />
          <SelectField label={t('ideas.format')} value={d.format ?? 'custom'} onChange={(v) => set({ format: v })} options={formats.map((c) => ({ value: c.key, label: lang === 'fa' ? c.fa : c.en }))} />
          <NumberField label={t('ideas.episodes')} min={1} max={30} value={d.episodes ?? 5} onChange={(v) => set({ episodes: v ?? 5 })} />
          <TextField label={t('lib.tags')} ltr value={(d.tags ?? []).join(', ')} onChange={(v) => set({ tags: v.split(',').map((x) => x.trim()).filter(Boolean) })} />
          <SelectField label={t('ideas.best_style')} value={d.suggested_styles?.[0] ?? ''} onChange={(v) => set({ suggested_styles: v ? [v] : [] })} options={[{ value: '', label: '—' }, ...styles.map((s) => ({ value: s.key, label: lang === 'fa' ? s.name_fa || s.name_en : s.name_en || s.name_fa }))]} />
        </div>
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!valid} onClick={save}>{t('common.save')}</Button>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
        </div>
      </div>
    </Card>
  )
}
