import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { AreaField, Badge, Button, Card, ErrorState, Loading, Notice, NumberField, SelectField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery } from '../hooks'
import { ErrorLine, JobLine, usePL, word } from './kit'

interface Strategy { key: string; available: boolean; reason: string; title_fa: string; title_en: string; how_fa: string; how_en: string; gpu: boolean; licence: string }
interface Ref { id: number; kind: string; label: string; approved: boolean; url: string | null }
interface Lock { status: 'draft' | 'locked'; version: number; strategy: string; anchor: string; avoid: string; seed: number; palette: { role: string; hex: string; name: string }[]; refs: Record<string, number>; stick: Record<string, any>; source: string }
interface Check { id: number; character_name: string; ok: boolean; palette_score: number | null; structure_score: number | null; vision_score: number | null; notes: { code: string; role?: string; name?: string }[]; shot: number | null }
interface Ident { character: { id: number; name: string }; lock: Lock | null; references: Ref[]; strategies: Strategy[]; resolved: { strategy: string; why: string }; rig: { id: number; version: number } | null; recent_checks: Check[]; not_used: { key: string; title_en: string; reason_fa: string; reason_en: string }[] }
interface Opts { stick: { choices: Record<string, string[]>; limb_colours: string[]; defaults: Record<string, any>; expressions: string[]; poses: { key: string; fa: string; en: string }[]; backgrounds: { key: string; fa: string; en: string }[] } }

const REASON: Record<string, [string, string]> = {
  no_stick_spec: ['این شخصیت با کد کشیده نشده است.', 'This character is not drawn by code.'],
  no_approved_sheet: ['برگهٔ مدل لازم است.', 'A model sheet is needed.'],
  workflow_missing: ['گردش‌کار یا مدل روی هیچ رایانه‌ای آماده نیست.', 'The workflow or model is not ready on any computer.'],
  no_approved_lora: ['LoRAِ تأییدشده ندارد.', 'No approved LoRA.'],
}
const CODE: Record<string, [string, string]> = {
  colour_missing: ['رنگ نشانه در تصویر نیست', 'A signature colour is missing'],
  sheet_colours_differ: ['رنگ‌ها با برگهٔ مدل فرق دارد', 'Colours differ from the model sheet'],
  vision_differs: ['مدل بینایی می‌گوید شخصیت فرق دارد', 'The vision model says the character differs'],
  vision_not_run: ['بررسی عمیق اجرا نشد (مدل بینایی نصب نیست)', 'Deep check not run (no vision model installed)'],
}

const tx = (m: Record<string, [string, string]>, k: string): [string, string] => m[k] ?? [k, k]

/** The identity of one character: stick-figure editor, identity words, colour key, model sheets, strategy and the lock. */
export function IdentityCard({ characterId, onChanged }: { characterId: number; onChanged?: () => void }) {
  const { L, pick, lang, f } = usePL()
  const q = useQuery<Ident>(`/characters/${characterId}/identity`)
  const opts = useQuery<Opts>('/identity/options')
  const act = useAction()
  const [edit, setEdit] = useState<Partial<Lock> | null>(null)
  const [showStick, setShowStick] = useState(false)
  const anchorJob = useJobRunner({ onFinished: () => q.reload() })
  const sheetJob = useJobRunner({ onFinished: () => q.reload() })
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data || !opts.data) return <Loading />
  const d = q.data
  const lock = d.lock
  const locked = lock?.status === 'locked'
  const set = (nd: Ident) => { q.setData(nd); onChanged?.() }
  const call = async (path: string, body: unknown = {}, method: 'post' | 'patch' = 'post') => {
    const nd = await act.run(() => (method === 'post' ? api.post<Ident>(`/characters/${characterId}/identity${path}`, body) : api.patch<Ident>(`/characters/${characterId}/identity${path}`, body)))
    if (nd) { set(nd); setEdit(null) }
    return nd
  }
  const sheets = d.references.filter((r) => r.kind === 'sheet' || r.kind === 'image')
  const exprs = d.references.filter((r) => r.kind === 'expression')
  const chosen = d.strategies.find((s) => s.key === d.resolved.strategy)
  return (
    <div className="stack-sm identity-card">
      <div className="row between">
        <b>{L('هویت و ثبات شخصیت', 'Identity and consistency')}</b>
        <span className="row nw">
          {lock && <Badge>v{lock.version}</Badge>}
          <Badge tone={locked ? 'ok' : lock ? 'warn' : 'neutral'}>{locked ? L('قفل‌شده', 'Locked') : lock ? L('پیش‌نویس', 'Draft') : L('بدون هویت', 'No identity')}</Badge>
        </span>
      </div>
      <p className="small muted">{L('برگهٔ مدل یک بار ساخته و تأیید می‌شود؛ بعد در هر تصویر و ویدئو همان شخصیت می‌آید. «قفل» یعنی این مرجعِ تأییدشده است.', 'The model sheet is made and approved once; then every picture and clip shows the same character. «Locked» means this reference is approved.')}</p>
      <div className="row">
        <Button size="sm" icon="users" disabled={locked} onClick={() => setShowStick((v) => !v)}>{lock?.stick && Object.keys(lock.stick).length ? L('ویرایش آدمک چوبی', 'Edit the stick figure') : L('ساخت با آدمک چوبی (بدون GPU)', 'Make as a stick figure (no GPU)')}</Button>
        <Button size="sm" icon="spark" disabled={locked} busy={anchorJob.busy} onClick={() => anchorJob.start(() => api.post(`/characters/${characterId}/identity/anchor`, {}))}>{L('نوشتن هویت با هوش مصنوعی', 'Write the identity with AI')}</Button>
        <Button size="sm" icon="image" disabled={locked || !lock?.anchor} busy={sheetJob.busy} onClick={() => sheetJob.start(() => api.post(`/characters/${characterId}/identity/sheets`, {}))}>{L('ساخت برگهٔ مدل با مدل تصویر', 'Make model sheets with the image model')}</Button>
        {!locked ? <Button size="sm" variant="primary" icon="check" busy={act.busy} disabled={!lock || (!lock.anchor.trim())} onClick={() => call('/lock')}>{L('تأیید و قفل هویت', 'Approve and lock the identity')}</Button>
          : <Button size="sm" busy={act.busy} onClick={() => call('/unlock')}>{L('باز کردن قفل', 'Unlock')}</Button>}
      </div>
      <JobLine job={anchorJob.job} offline={anchorJob.offline} />
      <JobLine job={sheetJob.job} offline={sheetJob.offline} />
      {showStick && !locked && <StickEditor characterId={characterId} opts={opts.data} start={lock?.stick ?? {}} onSaved={(nd) => { set(nd); setShowStick(false) }} />}
      {lock && (
        <div className="grid2">
          <div className="stack-sm">
            <b className="small">{L('تصویرهای مرجع', 'Reference pictures')}</b>
            <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
              {d.references.filter((r) => r.url).map((r) => (
                <a key={r.id} href={r.url!} target="_blank" rel="noreferrer" title={r.label} className="ref-thumb">
                  <img src={r.url!} alt={r.label} style={{ width: 120, height: 80, objectFit: 'cover', borderRadius: 8, border: r.id === lock.refs.sheet ? '3px solid var(--ok, #2e9e5b)' : '1px solid #8886' }} />
                </a>
              ))}
              {d.references.length === 0 && <span className="small muted">{L('هنوز تصویری نیست.', 'No pictures yet.')}</span>}
            </div>
            <div className="row">
              <SelectField label={L('برگهٔ مدل اصلی', 'Main model sheet')} disabled={locked} value={String(lock.refs.sheet ?? '')} onChange={(v) => api.post<Ident>(`/characters/${characterId}/identity/refs`, { sheet: v ? Number(v) : '' }).then(set).catch(() => undefined)} options={[{ value: '', label: '—' }, ...sheets.map((r) => ({ value: String(r.id), label: r.label || `#${r.id}` }))]} />
              <SelectField label={L('برگهٔ حالت چهره', 'Expression sheet')} disabled={locked} value={String(lock.refs.expressions ?? '')} onChange={(v) => api.post<Ident>(`/characters/${characterId}/identity/refs`, { expressions: v ? Number(v) : '' }).then(set).catch(() => undefined)} options={[{ value: '', label: '—' }, ...exprs.map((r) => ({ value: String(r.id), label: r.label || `#${r.id}` }))]} />
            </div>
          </div>
          <div className="stack-sm">
            <b className="small">{L('کلید رنگ', 'Colour key')}</b>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {lock.palette.map((p, i) => <span key={i} className="row nw small"><i style={{ width: 18, height: 18, borderRadius: 5, background: p.hex, border: '1px solid #8886', display: 'inline-block' }} /> {word(lang, p.role, f.num)} <code className="ltr">{p.hex}</code></span>)}
              {lock.palette.length === 0 && <span className="small muted">{L('خالی', 'Empty')}</span>}
            </div>
            <Button size="sm" variant="ghost" disabled={locked || !lock.refs.sheet} busy={act.busy} onClick={() => call('/palette', { apply: true })}>{L('استخراج رنگ‌ها از برگهٔ مدل', 'Extract the colours from the model sheet')}</Button>
          </div>
        </div>
      )}
      {lock && (
        <Card soft title={L('کلمات هویت', 'Identity words')}>
          {edit && !locked ? (
            <div className="stack-sm">
              <AreaField label={L('توصیف هویت (انگلیسی، برای مدل تصویر)', 'Identity words (English, for the image model)')} value={edit.anchor ?? lock.anchor} onChange={(v) => setEdit({ ...edit, anchor: v })} />
              <AreaField label={L('چه چیزی هرگز نباید عوض شود یا بیاید', 'What must never change or appear')} compact value={edit.avoid ?? lock.avoid} onChange={(v) => setEdit({ ...edit, avoid: v })} />
              <NumberField label={L('دانهٔ ثابت', 'Fixed seed')} value={edit.seed ?? lock.seed} onChange={(v) => setEdit({ ...edit, seed: v ?? 0 })} />
              <div className="row"><Button variant="primary" busy={act.busy} onClick={() => call('', edit, 'patch')}>{L('ذخیره', 'Save')}</Button><Button onClick={() => setEdit(null)}>{L('انصراف', 'Cancel')}</Button></div>
            </div>
          ) : (
            <div className="stack-sm">
              <div style={{ whiteSpace: 'pre-wrap' }} className="ltr">{lock.anchor || '—'}</div>
              {lock.avoid && <div className="small muted ltr">{L('پرهیز: ', 'Avoid: ')}{lock.avoid}</div>}
              <div className="small muted">{L('دانه: ', 'Seed: ')}<code className="ltr">{lock.seed}</code></div>
              {!locked && <div><Button size="sm" icon="edit" onClick={() => setEdit({})}>{L('ویرایش', 'Edit')}</Button></div>}
            </div>
          )}
        </Card>
      )}
      <Card soft title={L('راهبرد ثبات', 'Consistency strategy')}>
        <div className="stack-sm">
          <SelectField label={L('راهبرد دلخواه', 'Preferred strategy')} disabled={locked} value={lock?.strategy ?? 'auto'} onChange={(v) => call('', { strategy: v }, 'patch')}
            options={[{ value: 'auto', label: L('خودکار (قوی‌ترین گزینهٔ ممکن)', 'Automatic (the strongest one that can run)') }, ...d.strategies.map((s) => ({ value: s.key, label: pick(s as any, 'title') }))]} />
          {chosen && <Notice tone="info">{L('الان استفاده می‌شود: ', 'In use now: ')}<b>{pick(chosen as any, 'title')}</b> — {pick(chosen as any, 'how')}</Notice>}
          <table className="table small"><tbody>
            {d.strategies.map((s) => (
              <tr key={s.key}><td>{pick(s as any, 'title')}</td><td><Badge tone={s.available ? 'ok' : 'neutral'}>{s.available ? L('آماده', 'Ready') : L('آماده نیست', 'Not ready')}</Badge></td>
                <td className="muted">{!s.available && s.reason ? L(...tx(REASON, s.reason)) : s.gpu ? L('نیاز به GPU', 'Needs a GPU') : L('بدون GPU', 'No GPU')}</td></tr>))}
          </tbody></table>
          <details><summary className="small muted">{L('چرا IP-Adapter FaceID / PuLID استفاده نمی‌شود؟', 'Why are IP-Adapter FaceID / PuLID not used?')}</summary>
            {d.not_used.map((n) => <p key={n.key} className="small"><b>{n.title_en}</b>: {L(n.reason_fa, n.reason_en)}</p>)}</details>
        </div>
      </Card>
      {d.recent_checks.length > 0 && (
        <Card soft title={L('بررسی‌های اخیر ثبات', 'Recent consistency checks')}>
          {d.recent_checks.slice(0, 6).map((c) => (
            <div key={c.id} className="row between small"><span>{L('نما', 'Shot')} {c.shot ?? '—'}</span><span className="row nw"><Badge tone={c.ok ? 'ok' : 'err'}>{c.ok ? L('درست', 'OK') : L('ناهماهنگ', 'Drifts')}</Badge>
              {c.notes.map((n, i) => <span key={i} className="muted">{L(...tx(CODE, n.code))}{n.name ? ` (${word(lang, n.name)})` : ''}</span>)}</span></div>))}
        </Card>
      )}
      <ErrorLine text={act.error || anchorJob.startError || sheetJob.startError} />
    </div>
  )
}

function StickEditor({ characterId, opts, start, onSaved }: { characterId: number; opts: Opts; start: Record<string, any>; onSaved: (d: Ident) => void }) {
  const { L, lang } = usePL()
  const act = useAction()
  const o = opts.stick
  const [spec, setSpec] = useState<Record<string, any>>({ ...o.defaults, ...start })
  const [pose, setPose] = useState('stand')
  const [expr, setExpr] = useState('neutral')
  const [bg, setBg] = useState('plain')
  const [img, setImg] = useState<string>('')
  const [anchor, setAnchor] = useState('')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      api.post<{ url: string; anchor: string }>('/stick/preview', { spec, pose, expression: expr, background: bg }).then((r) => { setImg(r.url); setAnchor(r.anchor) }).catch(() => undefined)
    }, 350)
    return () => window.clearTimeout(timer.current)
  }, [spec, pose, expr, bg])
  const set = (k: string, v: unknown) => setSpec((s) => ({ ...s, [k]: v }))
  const CH: [string, string, string][] = [['head_style', 'شکل سر', 'Head'], ['eye_style', 'چشم', 'Eyes'], ['hat', 'کلاه', 'Hat'], ['hair', 'مو', 'Hair'], ['neck', 'دور گردن', 'Neck'], ['extra', 'اضافه', 'Extra'], ['prop', 'وسیله در دست', 'Prop']]
  const COL: [string, string, string][] = [['limb_colour', 'رنگ دست و پا', 'Limb colour'], ['head_fill', 'رنگ سر', 'Head colour'], ['hat_colour', 'رنگ کلاه', 'Hat colour'], ['hair_colour', 'رنگ مو', 'Hair colour'], ['neck_colour', 'رنگ شال/کراوات', 'Scarf/tie colour'], ['extra_colour', 'رنگ اضافه', 'Extra colour']]
  return (
    <Card title={L('آدمک چوبی اورجینال', 'Original stick figure')}>
      <div className="grid2">
        <div className="stack-sm">
          <div className="row" style={{ flexWrap: 'wrap' }}>
            {CH.map(([k, fa, en]) => <SelectField key={k} label={L(fa, en)} value={String(spec[k] ?? '')} onChange={(v) => set(k, v)} options={(o.choices[k] ?? []).map((x) => ({ value: x, label: word(lang, x) }))} />)}
          </div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            {COL.map(([k, fa, en]) => (
              <label key={k} className="field"><span className="label">{L(fa, en)}</span>
                <input type="color" value={String(spec[k] ?? '#000000')} onChange={(e) => set(k, e.target.value)} aria-label={L(fa, en)} /></label>))}
          </div>
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>{o.limb_colours.map((c) => <button key={c} type="button" aria-label={c} onClick={() => set('limb_colour', c)} style={{ width: 26, height: 26, borderRadius: 7, background: c, border: '2px solid #fff6', cursor: 'pointer' }} />)}</div>
          <div className="row">
            <SelectField label={L('ژست', 'Pose')} value={pose} onChange={setPose} options={o.poses.map((p) => ({ value: p.key, label: lang === 'fa' ? p.fa : p.en }))} />
            <SelectField label={L('حالت چهره', 'Expression')} value={expr} onChange={setExpr} options={o.expressions.map((x) => ({ value: x, label: word(lang, x) }))} />
            <SelectField label={L('پس‌زمینهٔ پیش‌نمایش', 'Preview background')} value={bg} onChange={setBg} options={o.backgrounds.map((b) => ({ value: b.key, label: lang === 'fa' ? b.fa : b.en }))} />
          </div>
          <p className="small muted ltr">{anchor}</p>
        </div>
        <div className="stack-sm" style={{ alignItems: 'center' }}>{img ? <img src={img} alt={L('پیش‌نمایش آدمک', 'Stick figure preview')} style={{ maxWidth: '100%', borderRadius: 12 }} /> : <Loading />}</div>
      </div>
      <div className="row" style={{ marginBlockStart: '1rem' }}>
        <Button variant="primary" icon="save" busy={act.busy} onClick={async () => { const d = await act.run(() => api.post<Ident>(`/characters/${characterId}/identity/stick`, { spec })); if (d) onSaved(d) }}>{L('ساخت عروسک، برگهٔ مدل و رنگ‌ها', 'Build the puppet, the model sheet and the colours')}</Button>
      </div>
      <ErrorLine text={act.error} />
    </Card>
  )
}

interface CRow { shot: number; label: string; keyframe_url: string | null; stale: boolean; characters: { id: number; name: string; lock_version: number; check: Check | null }[] }
interface CReport { shots: CRow[]; flagged: number[]; checked: number; ok: number; locked_characters: string[] }

/** The consistency board of an episode: every shot's picture, the locked characters in it and whether they still look like their reference. */
export function ConsistencyBoard({ episodeId }: { episodeId: number }) {
  const { L } = usePL()
  const q = useQuery<CReport>(`/episodes/${episodeId}/consistency`)
  const act = useAction()
  if (!q.data) return q.error ? <ErrorState error={q.error} onRetry={q.reload} /> : <Loading />
  const r = q.data
  const run = async (deep: boolean) => { const d = await act.run(() => api.post<CReport>(`/episodes/${episodeId}/consistency/run`, { deep })); if (d) q.setData(d) }
  const retakes = async () => { const d = await act.run(() => api.post<{ opened: number; report: CReport }>(`/episodes/${episodeId}/consistency/retakes`, {}), { success: L('درخواست بازسازی ثبت شد.', 'Retake requests opened.') }); if (d) q.setData(d.report) }
  return (
    <Card soft title={L('بررسی ثبات شخصیت‌ها', 'Character consistency check')}>
      <div className="stack-sm">
        {r.locked_characters.length === 0 ? <Notice tone="info">{L('هیچ شخصیتِ قفل‌شده‌ای در این قسمت نیست؛ هویت را در تب «شخصیت‌ها»ی صفحه قفل کنید.', 'No locked character appears in this episode; lock identities in the page\'s Characters tab.')}</Notice> : (
          <>
            <div className="row">
              <Badge tone="info">{L('بررسی‌شده', 'Checked')} {r.checked}</Badge><Badge tone="ok">{L('درست', 'OK')} {r.ok}</Badge><Badge tone={r.flagged.length ? 'err' : 'neutral'}>{L('نشان‌شده', 'Flagged')} {r.flagged.length}</Badge>
              <Button size="sm" icon="refresh" busy={act.busy} onClick={() => run(false)}>{L('بررسی', 'Check')}</Button>
              <Button size="sm" busy={act.busy} onClick={() => run(true)}>{L('بررسی عمیق (مدل بینایی)', 'Deep check (vision model)')}</Button>
              {r.flagged.length > 0 && <Button size="sm" variant="primary" busy={act.busy} onClick={retakes}>{L('ثبت درخواست بازسازی برای نشان‌شده‌ها', 'Open retake requests for the flagged shots')}</Button>}
            </div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 10 }}>
              {r.shots.filter((s) => s.characters.length).map((s) => {
                const bad = s.characters.some((c) => c.check && !c.check.ok)
                return (
                  <div key={s.shot} className="stack-sm" style={{ width: 120 }}>
                    {s.keyframe_url ? <img src={s.keyframe_url} alt={s.label} style={{ width: 120, height: 150, objectFit: 'cover', borderRadius: 8, border: bad ? '3px solid var(--err, #d94a3d)' : '1px solid #8886' }} /> : <div className="muted small">—</div>}
                    <div className="small">{s.label} {s.stale && <Badge tone="warn">{L('کهنه', 'old')}</Badge>}</div>
                    {s.characters.map((c) => <div key={c.id} className="small"><Badge tone={!c.check ? 'neutral' : c.check.ok ? 'ok' : 'err'}>{c.name}</Badge></div>)}
                  </div>)
              })}
            </div>
          </>
        )}
        <ErrorLine text={act.error} />
      </div>
    </Card>
  )
}
