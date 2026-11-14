import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Badge, Button, Loading, Notice, type Tone } from '../components/ui'
import { useJobRunner, useQuery } from '../hooks'
import { JobLine, usePL } from '../pipeline/kit'

type Verdict = 'ok' | 'warn' | 'fail' | 'skip' | 'pending'
interface Row { key: string; group: 'pc' | 'tools' | 'gpu'; fa: string; en: string; verdict: Verdict; reason_fa: string; reason_en: string; seconds: number; at: string | null }
interface Summary { ok: number; warn: number; fail: number; skip: number; pending: number; state: 'sound' | 'attention' | 'waiting' | 'problems' }
interface Payload {
  report: { stamp: string; version: string; finished_at: string; checks: Row[]; summary: Summary; ok: boolean; machine?: { gpu?: string } } | null
  running: boolean
  stale: boolean
  state: Summary['state'] | null
}

const TONE: Record<Verdict, Tone> = { ok: 'ok', warn: 'warn', fail: 'err', skip: 'neutral', pending: 'info' }

/** One look at this PC's automatic self-test: what was really tried, what passed, and what WAITS (the GPU PC is off, Ollama is not running ...) and starts by itself. */
export function PcSelfTestCard() {
  const { L, lang, n } = usePL()
  const q = useQuery<Payload>('/system/selftest', { interval: (d) => (d?.running ? 4000 : false) })
  const runner = useJobRunner({ onFinished: () => q.reload() })
  const rep = q.data?.report
  const text: Record<Verdict, string> = { ok: L('درست', 'Passed'), warn: L('هشدار', 'Warning'), fail: L('خطا', 'Failed'), skip: L('اجرا نمی‌شود', 'Not applicable'), pending: L('منتظر', 'Waiting') }
  const groups: { key: Row['group']; fa: string; en: string; hint_fa: string; hint_en: string }[] = [
    { key: 'pc', fa: 'پایه', en: 'Basics', hint_fa: 'روی هر رایانه‌ای اجرا می‌شود.', hint_en: 'Runs on any PC.' },
    { key: 'tools', fa: 'ابزار ویدئو با کد', en: 'Code-to-video tools', hint_fa: 'بعد از نصب خودکار Node.js و مرورگر.', hint_en: 'After Node.js and the browser are installed by themselves.' },
    { key: 'gpu', fa: 'کارت گرافیک و مدل‌ها', en: 'Graphics card and models', hint_fa: 'وقتی رایانهٔ GPUدار روشن و Ollama / ComfyUI آماده باشد.', hint_en: 'When the GPU PC is on and Ollama / ComfyUI are ready.' },
  ]
  return (
    <section className="card stack-sm" aria-label={L('آزمون خودکار این رایانه', 'Automatic self-test of this PC')} data-testid="pc-selftest">
      <div className="row between">
        <h2>{L('آزمون خودکار این رایانه', 'Automatic self-test of this PC')}</h2>
        <span className="row">
          <StateBadge state={rep?.summary.state ?? null} summary={rep?.summary} />
          {q.data?.running && <Badge tone="info">{L('در حال اجرا…', 'Running…')}</Badge>}
        </span>
      </div>
      <p className="small muted">{L('برنامه خودش، با کارهای واقعیِ کوچک، می‌سنجد که روی همین رایانه کار می‌کند: رمزگذاری ویدئو، متن فارسی، به‌روزرسانی خودکار، ابزار Remotion و ـ وقتی رایانهٔ GPUدار روشن شود ـ کارت گرافیک، مدل Ollama و ComfyUI. هر بررسی‌ای که منتظر چیزی است، همین که آماده شد خودکار اجرا می‌شود؛ چیزی را لازم نیست بزنید.',
        'The app tries small real jobs on this PC by itself: video encoding, Persian text, the automatic update, the Remotion tools and - once the GPU PC is on - the graphics card, the Ollama model and ComfyUI. A check that waits for something runs by itself as soon as it can; you do not need to press anything.')}</p>
      {!q.data ? <Loading /> : !rep ? <Notice tone="info">{L('هنوز اجرا نشده؛ تا چند دقیقهٔ دیگر خودکار اجرا می‌شود.', 'Not run yet; it starts by itself within a few minutes.')}</Notice> : (
        <div className="stack-sm">
          {rep.summary.state === 'waiting' && <Notice tone="info">{L(`تا اینجا چیزی خراب نیست؛ ${n(rep.summary.pending)} بررسی منتظر است و آماده که شد خودکار اجرا می‌شود.`, `Nothing is broken so far; ${rep.summary.pending} check${rep.summary.pending === 1 ? ' is' : 's are'} waiting and run${rep.summary.pending === 1 ? 's' : ''} by itself when ready.`)}</Notice>}
          {groups.map((g) => {
            const list = rep.checks.filter((c) => c.group === g.key)
            if (!list.length) return null
            return (
              <div key={g.key} className="stack-sm" data-group={g.key}>
                <h3>{L(g.fa, g.en)} <span className="small muted">{L(g.hint_fa, g.hint_en)}</span></h3>
                {list.map((c) => (
                  <div key={c.key} className="row between small" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }} data-testid={`pc-check-${c.key}`} data-verdict={c.verdict}>
                    <span><b>{L(c.fa, c.en)}</b><div className="muted">{L(c.reason_fa, c.reason_en)}</div></span>
                    <Badge tone={TONE[c.verdict] ?? 'neutral'}>{text[c.verdict] ?? c.verdict}</Badge>
                  </div>
                ))}
              </div>
            )
          })}
          <div className="small muted">{L('نسخه', 'Version')} {rep.version} · {new Date(rep.finished_at).toLocaleString(lang === 'fa' ? 'fa-IR' : 'en-US')}{q.data.stale ? ' · ' + L('نسخه عوض شده؛ به‌زودی دوباره آزمایش می‌شود', 'the version changed; it will be tested again soon') : ''}</div>
        </div>
      )}
      <div className="row">
        <Button size="sm" icon="spark" busy={runner.busy} onClick={() => runner.start(() => api.post<{ job: any }>('/system/selftest', {}))} data-testid="pc-selftest-run">{L('اجرای همین حالا', 'Run now')}</Button>
      </div>
      <JobLine job={runner.job} offline={runner.offline} />
    </section>
  )
}

function StateBadge({ state, summary }: { state: Summary['state'] | null; summary?: Summary }) {
  const { L, n } = usePL()
  if (!state || !summary) return null
  const label = { sound: L('همه‌چیز سالم', 'All sound'), attention: L(`سالم؛ ${n(summary.warn)} نکته`, `Sound; ${summary.warn} to look at`), waiting: L(`${n(summary.pending)} منتظر`, `${summary.pending} waiting`), problems: L(`${n(summary.fail)} خطا`, `${summary.fail} failed`) }[state]
  const tone = ({ sound: 'ok', attention: 'warn', waiting: 'info', problems: 'err' } as Record<string, Tone>)[state]
  return <span data-testid="pc-selftest-state" data-state={state}><Badge tone={tone}>{label}</Badge></span>
}

/** One line for the home screen: the state of the self-test and a link to the details. */
export function PcSelfTestStrip() {
  const { L } = usePL()
  const q = useQuery<Payload>('/system/selftest', { interval: (d) => (d?.running ? 5000 : false) })
  const rep = q.data?.report
  return (
    <div className="card flat row between" data-testid="pc-selftest-strip">
      <span className="row"><b>{L('آزمون خودکار این رایانه', 'Automatic self-test of this PC')}</b>
        {rep ? <StateBadge state={rep.summary.state} summary={rep.summary} /> : <Badge tone="info">{q.data ? L('هنوز اجرا نشده', 'Not run yet') : '…'}</Badge>}
      </span>
      <Link to="/system" className="small">{L('جزئیات', 'Details')}</Link>
    </div>
  )
}
