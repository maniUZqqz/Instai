import { useState } from 'react'
import { Badge, Button, ErrorState, Loading } from '../components/ui'
import { useQuery } from '../hooks'
import { usePL } from './kit'

export interface StoryTpl { key: string; genre: string; title_fa: string; title_en: string; blurb_fa: string; blurb_en: string; posts: number; endings: Record<string, number>; cast: { name: string; role: string; limb: string }[] }
export interface SeasonTpl { key: string; genre: string; title_fa: string; title_en: string; blurb_fa: string; blurb_en: string; episodes: number; runtime_sec: number; cast: { name: string; role: string; marker: string; limb: string }[] }

const END_FA: Record<string, string> = { good: 'خوب', bad: 'بد', secret: 'مخفی', neutral: 'خنثی' }
const END_EN: Record<string, string> = { good: 'good', bad: 'bad', secret: 'secret', neutral: 'neutral' }
const END_TONE: Record<string, 'ok' | 'err' | 'info' | 'neutral'> = { good: 'ok', bad: 'err', secret: 'info', neutral: 'neutral' }

function CastDots({ cast }: { cast: { name: string; limb: string }[] }) {
  return (
    <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
      {cast.map((c) => (
        <span key={c.name} className="row nw small" style={{ gap: 4 }}>
          <i aria-hidden style={{ width: 12, height: 12, borderRadius: 12, background: c.limb, display: 'inline-block', border: '1px solid #8886' }} />{c.name}
        </span>
      ))}
    </div>
  )
}

/** Ready-made, hand-written stories or seasons the owner can start from (they work with no text model; the characters come with their identity already drawn and locked). */
export function TemplateGallery({ kind, onPick, busy, label }: { kind: 'story' | 'season'; onPick: (key: string) => void; busy?: boolean; label?: string }) {
  const { L, n } = usePL()
  const q = useQuery<{ templates: (StoryTpl & SeasonTpl)[] }>(kind === 'story' ? '/choice/templates' : '/channel/templates')
  const [picked, setPicked] = useState('')
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Loading />
  return (
    <div className="grid-auto" role="list" aria-label={label ?? L('نمونه‌های آماده', 'Ready-made examples')}>
      {q.data.templates.map((t) => (
        <div key={t.key} role="listitem" className="card stack-sm" data-template={t.key}>
          <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
            <b>{L(t.title_fa, t.title_en)}</b>
            <Badge>{kind === 'story' ? `${n(t.posts)} ${L('پست', 'posts')}` : `${n(t.episodes)} ${L('قسمت', 'episodes')} · ${n(t.runtime_sec)} ${L('ثانیه', 's')}`}</Badge>
          </div>
          <div className="small muted">{L(t.blurb_fa, t.blurb_en)}</div>
          {kind === 'story' && (
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {Object.entries(t.endings).map(([k, c]) => <Badge key={k} tone={END_TONE[k] ?? 'neutral'}>{n(c)} {L('پایان ' + (END_FA[k] ?? k), (END_EN[k] ?? k) + ' ending')}</Badge>)}
            </div>
          )}
          <CastDots cast={t.cast} />
          <div><Button size="sm" variant="primary" icon="plus" busy={busy && picked === t.key} disabled={busy} onClick={() => { setPicked(t.key); onPick(t.key) }}>
            {kind === 'story' ? L('شروع با این داستان', 'Start with this story') : L('شروع با این فصل', 'Start with this season')}</Button></div>
        </div>
      ))}
    </div>
  )
}
