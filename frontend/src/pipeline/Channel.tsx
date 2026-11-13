import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PageDetail } from '../api/types'
import { useConfirm } from '../components/feedback'
import { AreaField, Badge, Button, Card, ErrorState, Loading, Notice, NumberField, SelectField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery } from '../hooks'
import { ErrorLine, JobLine, usePL } from './kit'
import { TemplateGallery } from './Templates'

interface Row { number: number; title: string; hook: string; logline: string; escalation: string; twist: string; cliffhanger: string; payoff_of_previous: string; characters: string[]; location: string; runtime_sec: number; opens: string[]; closes: string[]; episode_id?: number | null }
interface CastRow { character: number | null; name: string; role: string; marker: string; catchphrase: string }
interface Chan { id: number; genre: string; runtime_sec: number; episodes_per_season: number; season: number; cadence: { days: string[]; time: string; utc_offset: number; start: string }; cast: CastRow[]; rules: Record<string, number>; slate: Row[]; season_title: string; season_arc: string; status: 'draft' | 'planned' | 'approved'; applied: boolean }
interface Issue { code: string; episode?: number; [k: string]: unknown }
interface Payload { channel: Chan; validation: { ok: boolean; errors: Issue[]; warnings: Issue[]; threads: { id: string; opened: number | null; closed: number | null; span: number | null }[] }; schedule: { number: number; local: string }[]; beats: { name: string; start_sec: number; end_sec: number; seconds: number }[]; per_week: number; genre: { title_fa: string; title_en: string; summary_fa: string; summary_en: string; runtime: { min: number; default: number; max: number }; hook_sec: number; cliffhanger_sec: number; pacing: { avg_shot_sec: number; cuts_per_10s: number } } }
interface Conv { genres: { key: string; title_fa: string; title_en: string }[]; conventions: { key: string; fa: string; en: string }[]; cast_roles: string[] }

const DAYS = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri']
const DAY_FA: Record<string, string> = { sat: 'شنبه', sun: 'یکشنبه', mon: 'دوشنبه', tue: 'سه‌شنبه', wed: 'چهارشنبه', thu: 'پنجشنبه', fri: 'جمعه' }
const DAY_EN: Record<string, string> = { sat: 'Sat', sun: 'Sun', mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri' }
const ROLE_FA: Record<string, string> = { protagonist: 'قهرمان', rival: 'رقیب', ally: 'هم‌پیمان', comic: 'بامزه', villain: 'شرور', mentor: 'راهنما' }
const ROLE_EN: Record<string, string> = { protagonist: 'Protagonist', rival: 'Rival', ally: 'Ally', comic: 'Comic relief', villain: 'Villain', mentor: 'Mentor' }
const BEAT_FA: Record<string, string> = { hook: 'قلاب', setup: 'مقدمه', escalation: 'تشدید', twist: 'چرخش', crisis: 'بحران', cliffhanger: 'پایان باز' }
const BEAT_EN: Record<string, string> = { hook: 'Hook', setup: 'Setup', escalation: 'Escalation', twist: 'Twist', crisis: 'Crisis', cliffhanger: 'Cliffhanger' }
const ISSUE: Record<string, [string, string]> = {
  no_episodes: ['هنوز قسمتی طرح نشده است.', 'No episodes are planned yet.'],
  numbering: ['شمارهٔ قسمت‌ها پیوسته نیست.', 'The episode numbers are not consecutive.'],
  missing_hook: ['قلاب (ثانیه‌های اول) ندارد.', 'There is no hook (first seconds).'],
  missing_cliffhanger: ['پایان باز ندارد.', 'There is no cliffhanger.'],
  no_payoff_of_previous: ['معلوم نیست پایان باز قسمت قبل چگونه جواب داده می‌شود.', 'It is not clear how the previous cliffhanger is answered.'],
  runtime_off: ['طول قسمت خارج از محدودهٔ این ژانر است.', 'The runtime is outside the genre\'s range.'],
  no_characters: ['هیچ شخصیتی در این قسمت نیست.', 'No character appears in this episode.'],
  repeated_hook: ['قلاب تکراری است.', 'A hook is repeated.'],
  repeated_cliffhanger: ['پایان باز تکراری است.', 'A cliffhanger is repeated.'],
  location_repeat: ['سه قسمت پشت‌سرهم در یک مکان.', 'Three episodes in a row in the same place.'],
  thread_never_closed: ['یک رشتهٔ داستانی (پرسشِ باز) هرگز بسته نمی‌شود.', 'A story thread (open question) is never closed.'],
  thread_closed_unopened: ['رشته‌ای بسته می‌شود که باز نشده بود.', 'A thread is closed that was never opened.'],
  thread_too_long: ['یک رشته بیش از حد باز می‌ماند.', 'A thread stays open too long.'],
  too_many_open_threads: ['هم‌زمان رشتهٔ باز زیاد است.', 'Too many threads open at once.'],
  cast_never_appears: ['یکی از شخصیت‌های گروه هیچ‌جا نمی‌آید.', 'A cast member never appears.'],
}
const tx = (k: string): [string, string] => ISSUE[k] ?? [k, k]

/** Mini-series channel mode of one series: genre format, recurring cast, posting schedule, the season slate with hooks and cliffhangers. */
export function ChannelTab({ seriesId, page }: { seriesId: number; page: PageDetail | undefined }) {
  const { L, n, lang } = usePL()
  const q = useQuery<Payload>(`/series/${seriesId}/channel`)
  const conv = useQuery<Conv>('/channel/conventions')
  const chars = useQuery<{ id: number; name: string }[]>(page ? `/pages/${page.id}/characters` : null)
  const castOptions = chars.data ?? page?.characters ?? []
  const act = useAction()
  const confirm = useConfirm()
  const planJob = useJobRunner({ onFinished: () => q.reload() })
  const [instruction, setInstruction] = useState('')
  const [slate, setSlate] = useState<Row[] | null>(null)
  const [sel, setSel] = useState(1)
  useEffect(() => { if (q.data) setSlate(q.data.channel.slate) }, [q.data])
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data || !conv.data || slate === null) return <Loading />
  const p = q.data
  const ch = p.channel
  const put = async (body: Record<string, unknown>) => { const d = await act.run(() => api.put<Payload>(`/series/${seriesId}/channel`, body)); if (d) q.setData(d); return d }
  const post = async (path: string, body: unknown = {}) => { const d = await act.run(() => api.post<Payload>(`/series/${seriesId}/channel/${path}`, body)); if (d) { q.setData(d); if (path === 'template') chars.reload() } }
  const dirty = JSON.stringify(slate) !== JSON.stringify(ch.slate)
  const setRow = (i: number, k: keyof Row, v: unknown) => setSlate(slate.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  const split = (s: string) => s.split(/[،,\n]/).map((x) => x.trim()).filter(Boolean)
  const row = slate[sel - 1]
  const issuesOf = (nr: number) => [...p.validation.errors.map((i): Issue & { err: boolean } => ({ ...i, err: true })), ...p.validation.warnings.map((i): Issue & { err: boolean } => ({ ...i, err: false }))].filter((i) => i.episode === nr)
  const globalIssues = [...p.validation.errors.map((i): Issue & { err: boolean } => ({ ...i, err: true })), ...p.validation.warnings.map((i): Issue & { err: boolean } => ({ ...i, err: false }))].filter((i) => !i.episode)
  const total = p.beats.length ? p.beats[p.beats.length - 1].end_sec : 1
  return (
    <div className="stack">
      <p className="muted">{L('حالت کانال: قسمت‌های کوتاه با شخصیت‌های اورجینالِ تکرارشونده، قلاب در ثانیه‌های اول، پایان باز و برنامهٔ انتشار ثابت. از «قواعد این ژانر» فقط ساختار (طول، ریتم، قلاب) الهام گرفته شده؛ چیزی از سریال‌های دیگر کپی نمی‌شود.',
        'Channel mode: short episodes with recurring ORIGINAL characters, a hook in the first seconds, an open ending and a fixed posting schedule. Only the structure (length, pacing, hooks) of the genre is used; nothing is copied from other series.')}</p>
      <Card title={L('فصل‌های آماده', 'Ready-made seasons')}>
        <div className="stack-sm">
          <p className="small muted">{L('یک فصل کامل با قسمت‌ها، قلاب‌ها، پایان‌های باز و شخصیت‌های اورجینال؛ بدون مدل هم کار می‌کند. شخصیت‌ها با هویتِ قفل‌شده ساخته می‌شوند و همهٔ ردیف‌ها قابل ویرایش‌اند. پیش از ادامه همان قواعد قلاب و رشته‌ها بررسی می‌شود.',
            'A whole season with episodes, hooks, cliffhangers and original characters; it works with no model. The characters come with a locked identity and every row can be edited. The same hook and thread rules are checked before you go on.')}</p>
          <TemplateGallery kind="season" busy={act.busy} onPick={async (key) => { if (ch.slate.length === 0 || await confirm({ title: L('برنامهٔ فعلی با فصل آماده جایگزین شود؟', 'Replace the current plan with the ready-made season?'), message: '', danger: true })) post('template', { key }) }} />
        </div>
      </Card>
      <Card title={L('قالب و قواعد ژانر', 'Format and genre rules')}>
        <div className="stack-sm">
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <SelectField label={L('ژانر', 'Genre')} value={ch.genre} onChange={(v) => put({ genre: v })} options={conv.data.genres.map((g) => ({ value: g.key, label: L(g.title_fa, g.title_en) }))} />
            <NumberField label={L('طول هر قسمت (ثانیه)', 'Episode length (s)')} min={8} max={120} value={ch.runtime_sec} onChange={(v) => v && put({ runtime_sec: v })} hint={`${L('بازهٔ این ژانر', 'genre range')}: ${n(p.genre.runtime.min)}–${n(p.genre.runtime.max)}`} />
            <NumberField label={L('تعداد قسمت‌های فصل', 'Episodes per season')} min={2} max={60} value={ch.episodes_per_season} onChange={(v) => v && put({ episodes_per_season: v })} />
          </div>
          <div className="small muted">{L(p.genre.summary_fa, p.genre.summary_en)} · {L('قلاب در ', 'hook within ')}{n(p.genre.hook_sec)}{L(' ثانیه، پایان باز در ', ' s, cliffhanger in the last ')}{n(p.genre.cliffhanger_sec)}{L(' ثانیهٔ آخر، برش هر ', ' s, a cut every ')}{n(p.genre.pacing.avg_shot_sec)}{L(' ثانیه', ' s')}</div>
          <div className="row" style={{ gap: 0, borderRadius: 10, overflow: 'hidden' }} dir="ltr" aria-label={L('خط زمانی قسمت', 'Episode timeline')}>
            {p.beats.map((b, i) => <div key={b.name} title={`${b.start_sec}–${b.end_sec}s`} style={{ width: `${(b.seconds / total) * 100}%`, background: ['#e8a22b', '#78829a', '#2f7fd1', '#8a4fd1', '#d94a3d', '#2e9e5b'][i % 6], color: '#fff', textAlign: 'center', fontSize: 12, padding: '6px 2px' }}>{lang === 'fa' ? BEAT_FA[b.name] ?? b.name : BEAT_EN[b.name] ?? b.name}</div>)}
          </div>
          <details><summary className="small">{L('قواعد ساختاری ژانر', 'Structural rules of the genre')}</summary>
            <ul className="small">{conv.data.conventions.map((c) => <li key={c.key}>{L(c.fa, c.en)}</li>)}</ul></details>
        </div>
      </Card>
      <Card title={L('گروه شخصیت‌های تکرارشونده', 'Recurring cast')}>
        <div className="stack-sm">
          {ch.cast.map((c, i) => (
            <div key={i} className="row" style={{ flexWrap: 'wrap' }}>
              <SelectField label={L('شخصیت', 'Character')} value={String(c.character ?? '')} onChange={(v) => put({ cast: ch.cast.map((x, j) => (j === i ? { ...x, character: Number(v) } : x)) })} options={castOptions.map((x) => ({ value: String(x.id), label: x.name }))} />
              <SelectField label={L('نقش', 'Role')} value={c.role} onChange={(v) => put({ cast: ch.cast.map((x, j) => (j === i ? { ...x, role: v } : x)) })} options={(conv.data?.cast_roles ?? []).map((r) => ({ value: r, label: lang === 'fa' ? ROLE_FA[r] : ROLE_EN[r] }))} />
              <TextField label={L('نشانهٔ بصری (مثلاً شال قرمز)', 'Visual marker (e.g. red scarf)')} value={c.marker} onChange={(v) => put({ cast: ch.cast.map((x, j) => (j === i ? { ...x, marker: v } : x)) })} />
              <TextField label={L('تکیه‌کلام اورجینال', 'Original catchphrase')} value={c.catchphrase} onChange={(v) => put({ cast: ch.cast.map((x, j) => (j === i ? { ...x, catchphrase: v } : x)) })} />
              <Button size="sm" variant="ghost" icon="trash" aria-label={L('حذف', 'Remove')} onClick={() => put({ cast: ch.cast.filter((_, j) => j !== i) })} />
            </div>))}
          <div><Button size="sm" icon="plus" disabled={!page || ch.cast.length >= 8} onClick={() => put({ cast: [...ch.cast, { character: page?.characters[0]?.id ?? null, name: '', role: 'ally', marker: '', catchphrase: '' }] })}>{L('افزودن عضو', 'Add a member')}</Button></div>
          <div className="small muted">{L('هویت و ظاهر هر شخصیت (رنگ، کلاه، شال) در تب «شخصیت‌ها»ی صفحه قفل می‌شود تا در همهٔ قسمت‌ها یکی باشد.', 'Each character\'s identity and look (colour, cap, scarf) is locked in the page\'s Characters tab so it stays the same in every episode.')}</div>
        </div>
      </Card>
      <Card title={L('برنامهٔ انتشار', 'Posting schedule')}>
        <div className="stack-sm">
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            {DAYS.map((d) => (
              <Button key={d} size="sm" variant={ch.cadence.days.includes(d) ? 'primary' : 'default'} aria-pressed={ch.cadence.days.includes(d)}
                onClick={() => put({ cadence: { days: ch.cadence.days.includes(d) ? ch.cadence.days.filter((x) => x !== d) : [...ch.cadence.days, d] } })}>{lang === 'fa' ? DAY_FA[d] : DAY_EN[d]}</Button>))}
          </div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <TextField label={L('ساعت (به وقت صفحه)', 'Time (page local time)')} type="time" value={ch.cadence.time} onChange={(v) => put({ cadence: { time: v } })} />
            <TextField label={L('تاریخ شروع (میلادی)', 'Start date')} type="date" value={ch.cadence.start} onChange={(v) => v && put({ cadence: { start: v } })} />
          </div>
          <div className="small muted">{n(p.per_week)} {L('قسمت در هفته', 'episodes a week')} · {p.schedule.slice(0, 4).map((s) => s.local.replace('T', ' ')).join(' · ')}{p.schedule.length > 4 ? ' …' : ''}</div>
          <div className="small muted">{L('برنامه فقط یادآوری است؛ هیچ‌چیز خودکار منتشر نمی‌شود.', 'The schedule is a reminder only; nothing is published automatically.')}</div>
        </div>
      </Card>
      <Card title={L('برنامهٔ فصل', 'Season plan')} actions={<Badge tone={ch.status === 'approved' ? 'ok' : ch.status === 'planned' ? 'warn' : 'neutral'}>{ch.status === 'approved' ? L('تأییدشده', 'Approved') : ch.status === 'planned' ? L('در حال بازبینی', 'In review') : L('پیش‌نویس', 'Draft')}</Badge>}>
        <div className="stack-sm">
          <TextField label={L('یادداشت برای طراح (اختیاری)', 'Note for the planner (optional)')} value={instruction} onChange={setInstruction} />
          <div className="row">
            <Button variant="primary" icon="spark" busy={planJob.busy} onClick={async () => { if (slate.length === 0 || await confirm({ title: L('برنامهٔ فعلی جایگزین شود؟', 'Replace the current plan?'), message: '', danger: true })) planJob.start(() => api.post(`/series/${seriesId}/channel/plan`, { instruction, language: lang })) }}>{slate.length ? L('طراحی دوبارهٔ فصل', 'Plan the season again') : L('طراحی فصل با هوش مصنوعی', 'Plan the season with AI')}</Button>
            {dirty && <Button icon="save" variant="primary" busy={act.busy} onClick={() => put({ slate })}>{L('ذخیرهٔ ویرایش‌ها', 'Save the edits')}</Button>}
          </div>
          <JobLine job={planJob.job} offline={planJob.offline} />
          {planJob.result && (planJob.result as any).fallback && <Notice tone="warn">{L('مدل جواب معتبر نداد؛ طرح پایه ساخته شد.', 'The model gave no valid answer; a basic plan was made.')}</Notice>}
          {slate.length > 0 && (
            <>
              <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
                {slate.map((r, i) => <Button key={r.number} size="sm" variant={sel === r.number ? 'primary' : 'default'} onClick={() => setSel(r.number)}>{n(r.number)}{issuesOf(r.number).some((x) => x.err) ? ' ⚠' : ''}</Button>)}
              </div>
              {row && (
                <div className="stack-sm card soft">
                  <b>{L('قسمت', 'Episode')} {n(row.number)}{p.schedule[sel - 1] ? ` · ${p.schedule[sel - 1].local.replace('T', ' ')}` : ''}</b>
                  <TextField label={L('عنوان', 'Title')} value={row.title} onChange={(v) => setRow(sel - 1, 'title', v)} />
                  <AreaField label={L('قلاب (ثانیه‌های اول)', 'Hook (first seconds)')} compact value={row.hook} onChange={(v) => setRow(sel - 1, 'hook', v)} />
                  <AreaField label={L('خلاصه', 'Logline')} compact value={row.logline} onChange={(v) => setRow(sel - 1, 'logline', v)} />
                  <div className="row" style={{ flexWrap: 'wrap' }}>
                    <AreaField label={L('تشدید', 'Escalation')} compact value={row.escalation} onChange={(v) => setRow(sel - 1, 'escalation', v)} />
                    <AreaField label={L('چرخش', 'Twist')} compact value={row.twist} onChange={(v) => setRow(sel - 1, 'twist', v)} />
                  </div>
                  <AreaField label={L('پایان باز (۳ ثانیهٔ آخر)', 'Cliffhanger (last 3 seconds)')} compact value={row.cliffhanger} onChange={(v) => setRow(sel - 1, 'cliffhanger', v)} />
                  <AreaField label={L('پاسخ به پایان بازِ قسمت قبل', 'Answer to the previous cliffhanger')} compact value={row.payoff_of_previous} onChange={(v) => setRow(sel - 1, 'payoff_of_previous', v)} />
                  <div className="row" style={{ flexWrap: 'wrap' }}>
                    <TextField label={L('شخصیت‌ها (با ویرگول)', 'Characters (comma separated)')} value={row.characters.join('، ')} onChange={(v) => setRow(sel - 1, 'characters', split(v))} />
                    <TextField label={L('مکان', 'Location')} value={row.location} onChange={(v) => setRow(sel - 1, 'location', v)} />
                    <NumberField label={L('طول (ثانیه)', 'Length (s)')} value={row.runtime_sec} onChange={(v) => setRow(sel - 1, 'runtime_sec', v ?? ch.runtime_sec)} />
                  </div>
                  <div className="row" style={{ flexWrap: 'wrap' }}>
                    <TextField label={L('پرسش‌هایی که باز می‌کند (کد)', 'Questions it opens (ids)')} value={row.opens.join('، ')} onChange={(v) => setRow(sel - 1, 'opens', split(v))} />
                    <TextField label={L('پرسش‌هایی که می‌بندد (کد)', 'Questions it closes (ids)')} value={row.closes.join('، ')} onChange={(v) => setRow(sel - 1, 'closes', split(v))} />
                  </div>
                  {issuesOf(row.number).map((i, k) => <Notice key={k} tone={i.err ? 'err' : 'warn'}>{L(...tx(i.code))}</Notice>)}
                </div>
              )}
              <div className="stack-sm">
                <b className="small">{L('رشته‌های داستانی (پرسش‌های باز)', 'Story threads (open questions)')}</b>
                <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>{p.validation.threads.map((t) => <Badge key={t.id} tone={t.closed ? 'ok' : 'err'}>{t.id}: {t.opened ? n(t.opened) : '?'} → {t.closed ? n(t.closed) : '…'}</Badge>)}</div>
              </div>
              {globalIssues.map((i, k) => <Notice key={k} tone={i.err ? 'err' : 'warn'}>{L(...tx(i.code))}{i.character ? ` (${String(i.character)})` : ''}</Notice>)}
              {p.validation.ok && !dirty && <Notice tone="ok">{L('قواعد قلاب، پایان باز و رشته‌ها برقرار است.', 'The hook, cliffhanger and thread rules are satisfied.')}</Notice>}
              <div className="row">
                {ch.status !== 'approved' ? <Button variant="primary" icon="check" busy={act.busy} disabled={!p.validation.ok || dirty} onClick={() => post('approve')}>{L('تأیید برنامهٔ فصل', 'Approve the season plan')}</Button> : <Button busy={act.busy} onClick={() => post('revoke')}>{L('برداشتن تأیید', 'Withdraw approval')}</Button>}
                <Button icon="film" busy={act.busy} disabled={ch.status !== 'approved'} onClick={() => post('apply')}>{ch.applied ? L('به‌روزرسانی قسمت‌ها', 'Update the episodes') : L('ساخت قسمت‌ها در مجموعه', 'Create the episodes in the series')}</Button>
              </div>
              {ch.applied && <Notice tone="ok">{L('قسمت‌ها ساخته شدند؛ بیت‌شیتِ هر قسمت از همین برنامه شروع می‌شود (تب «پلهٔ استودیو» قسمت).', 'The episodes were created; each beat sheet starts from this plan (the episode\'s Studio ladder tab).')}</Notice>}
            </>
          )}
          <ErrorLine text={act.error || planJob.startError} />
        </div>
      </Card>
    </div>
  )
}
