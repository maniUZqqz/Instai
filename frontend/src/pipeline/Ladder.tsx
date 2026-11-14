import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { StylePicker, type Look } from '../components/StylePicker'
import { useConfirm } from '../components/feedback'
import { AreaField, Badge, Button, Card, ErrorState, Loading, Notice, NumberField, SelectField, StringListField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery } from '../hooks'
import { ConsistencyBoard } from './Identity'
import { useLibrary, nm, vocab } from '../library'
import { ErrorLine, JobLine, STAGE_TONE, usePL, word } from './kit'

interface Col { key: string; label_fa: string; label_en: string; type: string; options?: string[] }
interface FieldSpec { key: string; label_fa: string; label_en: string; type: string; columns?: Col[] }
interface Ver { number: number; author: string; note: string; created_at: string; provenance?: Record<string, unknown> }
interface Stage {
  key: string; scope: string; phase: string; source: 'stored' | 'bridge'; gen: string | null; needs: string[]; status: 'empty' | 'draft' | 'approved' | 'stale'
  stale_reasons: { code: string; stage?: string }[]; blocked_by: string[]; version: number; approved_version: number; auto: boolean; needs_human: boolean; ready: boolean
  fa: string; en: string; term_fa: string; term_en: string; fields: FieldSpec[]; data: Record<string, any> | null; current: Ver | null; versions: Ver[]
}
interface Payload { phases: { key: string; fa: string; en: string }[]; stages: Stage[]; counts: Record<string, number>; blockers: string[]; level: string }
type Data = Record<string, any>

/** Where a bridged stage is made (a link target relative to the episode / series). */
const WHERE: Record<string, (id: number, scope: string) => { to: string; fa: string; en: string } | null> = {
  bible: (id) => ({ to: `/series/${id}#develop`, fa: 'اتاق توسعه', en: 'Development room' }),
  character_models: () => null,
  script: (id) => ({ to: `/episodes/${id}#script`, fa: 'فیلم‌نامه', en: 'Script tab' }),
  storyboard: (id) => ({ to: `/episodes/${id}#storyboard`, fa: 'استوری‌بورد', en: 'Storyboard tab' }),
  animatic: (id) => ({ to: `/episodes/${id}#studio`, fa: 'پیش‌تولید', en: 'Pre-production tab' }),
  design: (id) => ({ to: `/episodes/${id}#studio`, fa: 'پیش‌تولید', en: 'Pre-production tab' }),
  key_art: (id) => ({ to: `/episodes/${id}#production`, fa: 'تولید', en: 'Production tab' }),
  animation: (id) => ({ to: `/episodes/${id}#production`, fa: 'تولید', en: 'Production tab' }),
  compositing: (id) => ({ to: `/episodes/${id}#production`, fa: 'تولید', en: 'Production tab' }),
}

/** The studio ladder of a series (development stages) or of an episode (all stages): every output versioned and approved before the next one. */
export function LadderPanel({ scope, id }: { scope: 'series' | 'episode'; id: number; characters?: { id: number; name: string }[] }) {
  const { L } = usePL()
  const base = scope === 'series' ? `/series/${id}/ladder` : `/episodes/${id}/ladder`
  const q = useQuery<Payload>(base)
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Loading />
  const p = q.data
  return (
    <div className="stack">
      <p className="muted">{L('هر مرحله خروجی نسخه‌دار دارد و باید پیش از مرحلهٔ بعد تأیید شود. اگر مرحله‌ای پیش از خودش تغییر کند، تأییدِ بعدی‌ها «کهنه» می‌شود تا دوباره نگاهشان کنید.',
        'Every stage keeps its versions and must be approved before the next one. If an earlier stage changes, the approvals after it turn «stale» so you look at them again.')}</p>
      <div className="row">
        <Badge tone="ok">{L('تأییدشده', 'Approved')} {p.counts.approved ?? 0}</Badge>
        <Badge tone="warn">{L('پیش‌نویس', 'Draft')} {p.counts.draft ?? 0}</Badge>
        <Badge tone="err">{L('کهنه', 'Stale')} {p.counts.stale ?? 0}</Badge>
        <Badge>{L('خالی', 'Empty')} {p.counts.empty ?? 0}</Badge>
      </div>
      {p.phases.map((ph) => {
        const stages = p.stages.filter((s) => s.phase === ph.key)
        if (!stages.length) return null
        return (
          <section key={ph.key} className="stack-sm" aria-label={L(ph.fa, ph.en)}>
            <h3>{L(ph.fa, ph.en)}</h3>
            {stages.map((s) => <StageCard key={s.key} s={s} base={base} id={id} scope={scope} stages={p.stages} onChanged={q.reload} setPayload={(d) => q.setData(d)} />)}
          </section>
        )
      })}
      {scope === 'episode' && p.blockers.length > 0 && <Notice tone="info">{L('پیش از شروع تولید این مرحله‌ها باید تأیید شوند: ', 'Before production starts these stages must be approved: ')}{p.blockers.map((k) => { const st = p.stages.find((x) => x.key === k); return st ? L(st.fa, st.en) : k }).join(L('، ', ', '))}</Notice>}
      {scope === 'series' && <SelfTestCard />}
    </div>
  )
}

interface STRow { key: string; group: string; fa: string; en: string; verdict: 'ok' | 'warn' | 'fail' | 'skip' | 'pending'; reason_fa: string; reason_en: string; seconds: number; at: string | null }
interface STPayload { report: { stamp: string; version: string; finished_at: string; gpu_run_at: string | null; checks: STRow[]; summary: Record<string, number>; ok: boolean } | null; running: boolean; stale: boolean }
const VERDICT_TONE: Record<string, 'neutral' | 'ok' | 'warn' | 'err' | 'info'> = { ok: 'ok', warn: 'warn', fail: 'err', skip: 'neutral', pending: 'neutral' }

/** The automatic self-test of the studio pipeline: what was checked by itself, what passed, what was skipped and why (models not installed yet, GPU PC off). */
function SelfTestCard() {
  const { L, lang } = usePL()
  const q = useQuery<STPayload>('/studio/selftest', { interval: (d) => (d?.running ? 4000 : false) })
  const runner = useJobRunner({ onFinished: () => q.reload() })
  const text: Record<string, string> = { ok: L('درست', 'Passed'), warn: L('هشدار', 'Warning'), fail: L('خطا', 'Failed'), skip: L('رد شد', 'Skipped'), pending: L('منتظر', 'Waiting') }
  const run = (gpu: boolean) => runner.start(() => api.post<{ job: any }>('/studio/selftest', { gpu }))
  const rep = q.data?.report
  return (
    <section className="card stack-sm" aria-label={L('آزمون خودکار', 'Automatic self-test')} data-selftest>
      <div className="row between">
        <h3>{L('آزمون خودکار استودیو', 'Automatic studio self-test')}</h3>
        <span className="row">
          {rep && <Badge tone={rep.ok ? 'ok' : 'err'}>{rep.ok ? L('همه‌چیز سالم', 'All sound') : L('خطا دارد', 'Has failures')}</Badge>}
          {q.data?.running && <Badge tone="info">{L('در حال اجرا…', 'Running…')}</Badge>}
        </span>
      </div>
      <p className="small muted">{L('برنامه خودش این بخش‌ها را آزمایش می‌کند: بخش‌های بدون GPU با هر نسخهٔ تازه، و بخش‌های مدل (متن، تصویر، بینایی) به‌محض این‌که رایانهٔ GPU روشن و آماده شود. چیزی را لازم نیست بزنید.',
        'The app tests these by itself: the parts that need no GPU with every new version, and the model parts (text, image, vision) as soon as the GPU PC is on and ready. You do not need to press anything.')}</p>
      {!q.data ? <Loading /> : !rep ? <Notice tone="info">{L('هنوز اجرا نشده؛ تا چند دقیقهٔ دیگر خودکار اجرا می‌شود.', 'Not run yet; it starts by itself within a few minutes.')}</Notice> : (
        <div className="stack-sm">
          {rep.checks.map((c) => (
            <div key={c.key} className="row between small" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }} data-check={c.key}>
              <span><b>{L(c.fa, c.en)}</b><div className="muted">{L(c.reason_fa, c.reason_en)}</div></span>
              <Badge tone={VERDICT_TONE[c.verdict] ?? 'neutral'}>{text[c.verdict] ?? c.verdict}</Badge>
            </div>
          ))}
          <div className="small muted">{L('نسخه', 'Version')} {rep.version} · {new Date(rep.finished_at).toLocaleString(lang === 'fa' ? 'fa-IR' : 'en-US')}{q.data.stale ? ' · ' + L('محتوا عوض شده؛ به‌زودی دوباره آزمایش می‌شود', 'content changed; it will be tested again soon') : ''}</div>
        </div>
      )}
      <div className="row">
        <Button size="sm" icon="spark" busy={runner.busy} onClick={() => run(false)}>{L('اجرای همین حالا (بدون GPU)', 'Run now (no GPU)')}</Button>
        <Button size="sm" busy={runner.busy} onClick={() => run(true)}>{L('اجرا با GPU و مدل‌ها', 'Run with the GPU and models')}</Button>
      </div>
      <JobLine job={runner.job} offline={runner.offline} />
    </section>
  )
}

function StageCard({ s, base, id, scope, stages, onChanged, setPayload }: { s: Stage; base: string; id: number; scope: string; stages: Stage[]; onChanged: () => void; setPayload: (d: Payload) => void }) {
  const { L, lang } = usePL()
  const act = useAction()
  const confirm = useConfirm()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Data>({})
  const [note, setNote] = useState('')
  const [instruction, setInstruction] = useState('')
  const [showVersions, setShowVersions] = useState(false)
  const runner = useJobRunner({ onFinished: () => onChanged() })
  useEffect(() => { if (!editing) setDraft(s.data ?? {}) }, [s.data, editing])
  const names = s.blocked_by.map((k) => { const b = stages.find((x) => x.key === k); return b ? L(b.fa, b.en) : k })
  const call = async (path: string, body: unknown = {}, method: 'post' | 'put' = 'post') => {
    const d = await act.run(() => (method === 'post' ? api.post<Payload>(`${base}/${s.key}${path}`, body) : api.put<Payload>(`${base}/${s.key}${path}`, body)))
    if (d) setPayload(d)
    return d
  }
  const save = async () => { if (await call('', { data: draft, note: note || L('ویرایش دستی', 'Edited by hand') }, 'put')) { setEditing(false); setNote('') } }
  const generate = () => runner.start(() => api.post<{ job: any }>(`${base}/${s.key}/generate`, { instruction, language: lang }))
  const statusText = { empty: L('خالی', 'Empty'), draft: L('پیش‌نویس', 'Draft'), approved: L('تأییدشده', 'Approved'), stale: L('کهنه', 'Stale') }[s.status]
  const where = WHERE[s.key]?.(id, scope)
  return (
    <div className={'card stack-sm ladder-stage st-' + s.status}>
      <div className="row between" style={{ flexWrap: 'nowrap' }}>
        <button className="linklike strong" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{L(s.fa, s.en)}</button>
        <span className="row nw">
          {s.version > 0 && <Badge>v{s.version}</Badge>}
          {s.auto && <Badge tone="info">{L('خودکار', 'auto')}</Badge>}
          <Badge tone={STAGE_TONE[s.status]}>{statusText}</Badge>
        </span>
      </div>
      <div className="small muted">{L(s.term_fa, s.term_en)}</div>
      {s.stale_reasons.length > 0 && <Notice tone="warn">{s.stale_reasons.map((r) => r.code === 'changed' ? L('محتوا بعد از تأیید تغییر کرده است.', 'The content changed after it was approved.') :
        L(`مرحلهٔ «${(() => { const b = stages.find((x) => x.key === r.stage); return b ? b.fa : r.stage })()}» بعد از تأیید این مرحله تغییر کرده است.`, `The stage «${(() => { const b = stages.find((x) => x.key === r.stage); return b ? b.en : r.stage })()}» changed after this one was approved.`)).join(' ')}</Notice>}
      <div className="row">
        {s.gen && <Button size="sm" icon="spark" busy={runner.busy} onClick={generate}>{s.version ? L('نسخهٔ تازه با هوش مصنوعی', 'New version with AI') : L('نوشتن با هوش مصنوعی', 'Write with AI')}</Button>}
        {s.source === 'stored' && s.fields.length > 0 && <Button size="sm" icon="edit" onClick={() => { setOpen(true); setEditing((e) => !e) }}>{editing ? L('بستن ویرایش', 'Close editor') : L('ویرایش', 'Edit')}</Button>}
        {s.status !== 'empty' && s.status !== 'approved' && (
          <Button size="sm" variant="primary" icon="check" busy={act.busy} disabled={s.blocked_by.length > 0} onClick={() => call('/approve')}>{L('تأیید', 'Approve')}</Button>
        )}
        {s.status === 'approved' && <Button size="sm" busy={act.busy} onClick={async () => { if (await confirm({ title: L('تأیید این مرحله برداشته شود؟', 'Withdraw the approval of this stage?'), message: '', danger: true })) call('/revoke') }}>{L('برداشتن تأیید', 'Withdraw approval')}</Button>}
        {s.versions.length > 0 && <Button size="sm" variant="ghost" onClick={() => setShowVersions((v) => !v)}>{L('نسخه‌ها', 'Versions')} ({s.versions.length})</Button>}
        {where && <Link className="btn sm" to={where.to}>{L(where.fa, where.en)}</Link>}
      </div>
      {s.blocked_by.length > 0 && s.status !== 'approved' && <div className="small muted">{L('برای تأیید، اول این‌ها تأیید شوند: ', 'To approve, approve these first: ')}{names.join(L('، ', ', '))}</div>}
      {s.gen === 'llm' && open && <TextField label={L('یادداشت کارگردان برای نسخهٔ بعد (اختیاری)', "Director's note for the next version (optional)")} value={instruction} onChange={setInstruction} />}
      <JobLine job={runner.job} offline={runner.offline} />
      <ErrorLine text={act.error || runner.startError} />
      {open && (
        <div className="stack-sm">
          {editing ? (
            <>
              <StageFields s={s} data={draft} onChange={setDraft} />
              <TextField label={L('یادداشت این نسخه', 'Note for this version')} value={note} onChange={setNote} />
              <div className="row"><Button variant="primary" icon="save" busy={act.busy} onClick={save}>{L('ذخیره به‌عنوان نسخهٔ تازه', 'Save as a new version')}</Button><Button onClick={() => setEditing(false)}>{L('انصراف', 'Cancel')}</Button></div>
            </>
          ) : <StageView s={s} />}
          {s.key === 'key_art' && scope === 'episode' && <ConsistencyBoard episodeId={id} />}
          {s.key === 'character_models' && <CharacterModels s={s} />}
        </div>
      )}
      {showVersions && <Versions s={s} base={base} setPayload={setPayload} />}
    </div>
  )
}

function CharacterModels({ s }: { s: Stage }) {
  const { L, lang } = usePL()
  const rows = (s.data?.characters ?? []) as { id: number; name: string; status: string; version: number; source: string; anchor: string; palette: { hex: string; role: string }[] }[]
  if (!rows.length) return <Notice tone="info">{L('هنوز شخصیتی نیست. در تب «شخصیت‌ها»ی صفحه بسازید و هویتشان را قفل کنید.', 'No characters yet. Add them in the page\'s Characters tab and lock their identity.')}</Notice>
  return (
    <div className="stack-sm">
      {rows.map((r) => (
        <div key={r.id} className="row between small">
          <span className="strong">{r.name}</span>
          <span className="row nw">{r.palette.slice(0, 6).map((p, i) => <i key={i} title={word(lang, p.role)} style={{ width: 14, height: 14, borderRadius: 4, background: p.hex, display: 'inline-block', border: '1px solid #8886' }} />)}
            <Badge tone={r.status === 'locked' ? 'ok' : r.status === 'draft' ? 'warn' : 'neutral'}>{r.status === 'locked' ? L('قفل‌شده', 'Locked') : r.status === 'draft' ? L('پیش‌نویس', 'Draft') : L('بدون هویت', 'No identity')}</Badge></span>
        </div>
      ))}
      <div className="small muted">{L('هویت هر شخصیت در تب «شخصیت‌ها»ی صفحه ساخته و قفل می‌شود.', 'Each identity is made and locked in the page\'s Characters tab.')}</div>
    </div>
  )
}

function Versions({ s, base, setPayload }: { s: Stage; base: string; setPayload: (d: Payload) => void }) {
  const { L } = usePL()
  const act = useAction()
  const [shown, setShown] = useState<{ number: number; data: Data } | null>(null)
  const [diff, setDiff] = useState<{ a: number; b: number; changes: { path: string; before: unknown; after: unknown }[] } | null>(null)
  const authorText: Record<string, string> = { ai: L('هوش مصنوعی', 'AI'), human: L('شما', 'You'), system: L('خودکار', 'System') }
  return (
    <div className="stack-sm card soft">
      {s.versions.map((v) => (
        <div key={v.number} className="row between small" style={{ flexWrap: 'wrap' }}>
          <span><b>v{v.number}</b> · {authorText[v.author] ?? v.author} · {new Date(v.created_at).toLocaleString(L('fa-IR', 'en-US'))} {v.note && <span className="muted">— {v.note}</span>}</span>
          <span className="row">
            <Button size="sm" variant="ghost" onClick={async () => { const d = await act.run(() => api.get<{ data: Data }>(`${base}/${s.key}/versions/${v.number}`)); if (d) setShown({ number: v.number, data: d.data }) }}>{L('نمایش', 'View')}</Button>
            {v.number !== s.version && <Button size="sm" variant="ghost" onClick={async () => { const d = await act.run(() => api.get<{ a: number; b: number; changes: { path: string; before: unknown; after: unknown }[] }>(`${base}/${s.key}/diff?a=${v.number}&b=${s.version}`)); if (d) setDiff(d) }}>{L('مقایسه با فعلی', 'Compare with current')}</Button>}
            {s.source === 'stored' && v.number !== s.version && <Button size="sm" variant="ghost" busy={act.busy} onClick={async () => { const d = await act.run(() => api.post<Payload>(`${base}/${s.key}/restore`, { version: v.number })); if (d) setPayload(d) }}>{L('بازگردانی', 'Restore')}</Button>}
            {v.number !== s.approved_version && s.status !== 'empty' && s.source === 'stored' && <Button size="sm" variant="ghost" busy={act.busy} disabled={s.blocked_by.length > 0} onClick={async () => { const d = await act.run(() => api.post<Payload>(`${base}/${s.key}/approve`, { version: v.number })); if (d) setPayload(d) }}>{L('تأیید این نسخه', 'Approve this version')}</Button>}
          </span>
        </div>
      ))}
      {diff && (
        <div className="stack-sm"><b className="small">v{diff.a} → v{diff.b}</b>
          {diff.changes.length === 0 ? <span className="small muted">{L('بدون تفاوت', 'No difference')}</span> : diff.changes.map((c, i) => (
            <div key={i} className="small"><code className="ltr">{c.path}</code><div className="muted">− {JSON.stringify(c.before)}</div><div>+ {JSON.stringify(c.after)}</div></div>))}
        </div>
      )}
      {shown && <div className="small"><b>v{shown.number}</b><pre className="ltr" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(shown.data, null, 1)}</pre></div>}
      <ErrorLine text={act.error} />
    </div>
  )
}

/** The art style of the series as the owner reads it: the style's name, the realism level and the colour theme - never the internal keys. */
function StyleLine({ data }: { data: Data }) {
  const { L, lang } = usePL()
  const lib = useLibrary()
  const key = String(data.style_key ?? '')
  if (!lib.data) return key ? <div data-testid="ladder-style-line"><b className="small">{L('سبک هنری', 'Art style')}</b><div>…</div></div> : null     // names come with the library: never flash the raw keys
  const st = lib.style(key)
  const th = lib.theme(String(data.theme_key ?? ''))
  const parts = [st ? nm(st, lang) : key, vocab(lib.data?.realism, String(data.realism ?? ''), lang), th ? nm(th, lang) : ''].filter(Boolean)
  return key ? <div data-testid="ladder-style-line"><b className="small">{L('سبک هنری', 'Art style')}</b><div>{parts.join(' · ')}</div></div> : null
}

function StageView({ s }: { s: Stage }) {
  const { L, pick, lang } = usePL()
  const data = s.data
  if (!data) return <div className="small muted">{L('هنوز خروجی ندارد.', 'No output yet.')}</div>
  if (s.fields.length === 0) {
    return <pre className="small ltr" style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{JSON.stringify(data, null, 1).slice(0, 2500)}</pre>
  }
  const hasStyle = s.fields.some((f) => f.type === 'style')
  return (
    <div className="stack-sm">
      {s.fields.map((f) => {
        const v = data[f.key]
        if (f.type === 'style') return <StyleLine key={f.key} data={data} />
        if (hasStyle && (f.key === 'realism' || f.key === 'theme_key')) return null          // shown inside the style line, by name
        if (f.type === 'rows') {
          const rows = (v ?? []) as Data[]
          return (
            <div key={f.key} className="stack-sm"><b className="small">{pick(f as any)}</b>
              <div style={{ overflowX: 'auto' }}>
                <table className="table small"><thead><tr>{f.columns!.map((c) => <th key={c.key}>{pick(c as any)}</th>)}</tr></thead>
                  <tbody>{rows.map((r, i) => <tr key={i}>{f.columns!.map((c) => <td key={c.key}>{c.type === 'bool' ? (r[c.key] ? '✓' : '') : c.type === 'choice' ? word(lang, String(r[c.key] ?? '')) : String(r[c.key] ?? '')}</td>)}</tr>)}</tbody></table>
              </div>
            </div>
          )
        }
        const text = Array.isArray(v) ? v.join('\n') : String(v ?? '')
        return text ? <div key={f.key}><b className="small">{pick(f as any)}</b><div style={{ whiteSpace: 'pre-wrap' }}>{text}</div></div> : null
      })}
    </div>
  )
}

function StageFields({ s, data, onChange }: { s: Stage; data: Data; onChange: (d: Data) => void }) {
  const { L, pick } = usePL()
  const set = (k: string, v: unknown) => onChange({ ...data, [k]: v })
  return (
    <div className="stack-sm">
      {s.fields.map((f) => {
        const label = pick(f as any)
        if (f.type === 'rows') return <RowsEditor key={f.key} label={label} cols={f.columns!} rows={(data[f.key] ?? []) as Data[]} onChange={(r) => set(f.key, r)} />
        if (f.type === 'list') return <StringListField key={f.key} label={label} value={(data[f.key] ?? []) as string[]} onChange={(v) => set(f.key, v)} addLabel={L('افزودن', 'Add')} />
        if (f.type === 'number') return <NumberField key={f.key} label={label} value={data[f.key] ?? null} onChange={(v) => set(f.key, v)} />
        if (f.type === 'style') return <StylePicker key={f.key} showTheme name="ladder-look" value={{ style_key: data.style_key ?? '', realism: data.realism ?? '', theme_key: data.theme_key ?? '' } as Look} onChange={(v) => onChange({ ...data, ...v })} />
        if (f.type === 'text') return <TextField key={f.key} label={label} value={String(data[f.key] ?? '')} onChange={(v) => set(f.key, v)} />
        return <AreaField key={f.key} label={label} value={String(data[f.key] ?? '')} onChange={(v) => set(f.key, v)} />
      })}
    </div>
  )
}

function RowsEditor({ label, cols, rows, onChange }: { label: string; cols: Col[]; rows: Data[]; onChange: (r: Data[]) => void }) {
  const { L, pick, lang } = usePL()
  const setCell = (i: number, k: string, v: unknown) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  const blank = () => Object.fromEntries(cols.map((c) => [c.key, c.type === 'number' ? null : c.type === 'bool' ? false : '']))
  return (
    <div className="stack-sm">
      <b className="small">{label}</b>
      <div style={{ overflowX: 'auto' }}>
        <table className="table small">
          <thead><tr><th>#</th>{cols.map((c) => <th key={c.key}>{pick(c as any)}</th>)}<th /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                {cols.map((c) => (
                  <td key={c.key} style={{ minWidth: c.type === 'long' ? 220 : c.type === 'number' ? 80 : 120 }}>
                    {c.type === 'choice' ? <SelectField label="" aria-label={pick(c as any)} value={String(r[c.key] ?? '')} onChange={(v) => setCell(i, c.key, v)} options={[{ value: '', label: '—' }, ...(c.options ?? []).map((o) => ({ value: o, label: word(lang, o) }))]} />
                      : c.type === 'number' ? <NumberField label="" aria-label={pick(c as any)} value={r[c.key] ?? null} onChange={(v) => setCell(i, c.key, v)} />
                      : c.type === 'bool' ? <input type="checkbox" aria-label={pick(c as any)} checked={!!r[c.key]} onChange={(e) => setCell(i, c.key, e.target.checked)} />
                      : c.type === 'long' ? <AreaField label="" aria-label={pick(c as any)} compact value={String(r[c.key] ?? '')} onChange={(v) => setCell(i, c.key, v)} />
                      : <TextField label="" aria-label={pick(c as any)} value={String(r[c.key] ?? '')} onChange={(v) => setCell(i, c.key, v)} />}
                  </td>
                ))}
                <td><Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={L('حذف ردیف', 'Delete row')} onClick={() => onChange(rows.filter((_, j) => j !== i))} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div><Button size="sm" icon="plus" onClick={() => onChange([...rows, blank()])}>{L('ردیف تازه', 'Add a row')}</Button></div>
    </div>
  )
}
