import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Character, Episode, Script, ScriptBlock } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { Button, Card, Notice, Progress, TextField, AreaField } from '../../components/ui'
import { useAction } from '../../hooks'
import { useI18n } from '../../i18n'

const WORDS_PER_SEC = { fa: 2.4, other: 2.6 } // same reading speed as the server (agents/roles.py reading_stats)

function liveStats(d: Draft, lang: string, target: number) {
  const text = [...d.blocks.map((b) => b.text), d.cta].join(' ')
  const words = text.split(/\s+/).filter(Boolean).length
  const wps = lang.startsWith('fa') ? WORDS_PER_SEC.fa : WORDS_PER_SEC.other
  const est = Math.round((words / wps) * 10) / 10
  const warnings: string[] = []
  if (!d.hook.trim()) warnings.push('missing_hook')
  if (!d.cta.trim()) warnings.push('missing_cta')
  if (target && est > target * 1.25) warnings.push('too_long')
  if (target && est < target * 0.6) warnings.push('too_short')
  return { words, est, warnings }
}

interface Draft {
  title: string
  hook: string
  cta: string
  blocks: ScriptBlock[]
}

function toDraft(ep: Episode): Draft {
  const s = ep.script as Script
  return {
    title: s.title ?? ep.title,
    hook: s.hook ?? '',
    cta: s.cta ?? '',
    blocks: (s.blocks ?? []).map((b) => ({ speaker: b.speaker ?? '', text: b.text ?? '', emotion: b.emotion ?? '' })),
  }
}

const blank = (): ScriptBlock => ({ speaker: '', text: '', emotion: '' })

export function ScriptEditor({ ep, characters, editable, onSaved, onRewrite, onUnlock, rewriteBusy, onDirty }: {
  ep: Episode
  characters: Character[]
  editable: boolean
  onSaved: (e: Episode) => void
  onRewrite: () => void
  onUnlock: () => void
  rewriteBusy: boolean
  onDirty: (d: boolean) => void
}) {
  const { t, f, tr } = useI18n()
  const confirm = useConfirm()
  const hasScript = ((ep.script as Script).blocks ?? []).length > 0
  const [manual, setManual] = useState(false)
  const initial = useMemo(() => (hasScript ? toDraft(ep) : { title: ep.title, hook: '', cta: '', blocks: [blank(), blank(), blank()] }), [ep.id, ep.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const [d, setD] = useState<Draft>(initial)
  const saved = useMemo(() => JSON.stringify(hasScript ? toDraft(ep) : initial), [ep.updated_at, hasScript]) // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(d) !== saved
  useEffect(() => {
    onDirty(dirty)
    return () => onDirty(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty])
  const act = useAction()
  const stats = liveStats(d, ep.language, ep.duration_sec)
  const server = ep.script_checks
  const showServer = !dirty && hasScript && server.warnings
  const warnings = showServer ? (server.warnings as string[]) : stats.warnings
  const est = showServer && server.est_duration_sec != null ? server.est_duration_sec : stats.est
  const words = showServer && server.word_count != null ? server.word_count : stats.words
  const names = Array.from(new Set([t('script.narrator'), ...characters.map((c) => c.name)]))

  const setBlock = (i: number, patch: Partial<ScriptBlock>) => setD({ ...d, blocks: d.blocks.map((b, j) => (j === i ? { ...b, ...patch } : b)) })
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= d.blocks.length) return
    const b = [...d.blocks]
    ;[b[i], b[j]] = [b[j], b[i]]
    setD({ ...d, blocks: b })
  }

  if (!hasScript && !manual) {
    return (
      <Card>
        <div className="stack-sm">
          <p>{t('script.none')}</p>
          {editable && <div><Button onClick={() => setManual(true)}>{t('script.write_manual')}</Button></div>}
        </div>
      </Card>
    )
  }

  const save = async () => {
    const blocks = d.blocks.filter((b) => b.text.trim()).map((b) => ({ speaker: b.speaker.trim() || t('script.narrator'), text: b.text.trim(), emotion: b.emotion.trim() }))
    if (blocks.length === 0) return undefined
    return act.run(() => api.put<Episode>(`/episodes/${ep.id}/script`, { title: d.title.trim() || ep.title, hook: d.hook.trim() || blocks[0].text, cta: d.cta.trim(), blocks }), { success: t('common.saved') })
  }
  const doSave = async () => {
    const e = await save()
    if (e) onSaved(e)
  }
  const rewrite = async () => {
    if (await confirm({ message: t('script.rewrite_confirm'), confirmLabel: t('script.rewrite') })) onRewrite()
  }

  const pct = ep.duration_sec ? est / ep.duration_sec : 0
  return (
    <div className="stack">
      {!editable && (
        <Notice tone="info">
          <div className="row between">
            <span>{t('script.readonly')}</span>
            <Button size="sm" onClick={onUnlock}>{t('script.unlock')}</Button>
          </div>
        </Notice>
      )}
      <Card title={t('script.stats')}>
        <div className="stack-sm">
          <div className="row" style={{ gap: '1.5rem' }}>
            <span><b>{f.num(words)}</b> <span className="muted">{t('script.words')}</span></span>
            <span><b>{f.duration(est)}</b> <span className="muted">{t('script.estimated')}</span></span>
            <span><b>{f.duration(ep.duration_sec)}</b> <span className="muted">{t('script.target')}</span></span>
          </div>
          <Progress value={Math.min(1, pct)} tone={pct > 1.25 || pct < 0.6 ? 'warn' : 'ok'} label={t('script.estimated')} />
          <div className="small muted">{t('script.stats_note')}</div>
          {warnings.length === 0 ? (
            <Notice tone="ok">{t('script.ok')}</Notice>
          ) : (
            <div className="stack-sm" aria-live="polite">
              {warnings.map((w) => (
                <Notice key={w} tone="warn">{tr('script.warn_' + w, w)}</Notice>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card>
        <div className="stack">
          <TextField label={t('script.title')} value={d.title} onChange={(v) => setD({ ...d, title: v })} disabled={!editable} />
          <TextField label={t('script.hook')} value={d.hook} onChange={(v) => setD({ ...d, hook: v })} disabled={!editable} hint={t('script.hook_hint')} />
          <datalist id="speakers">{names.map((n) => <option key={n} value={n} />)}</datalist>
          <ol className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }} aria-label={t('script.blocks')}>
            {d.blocks.map((b, i) => (
              <li key={i} className="script-block">
                <div>
                  <div className="meta">
                    <TextField label={t('script.speaker')} list="speakers" value={b.speaker} onChange={(v) => setBlock(i, { speaker: v })} disabled={!editable} />
                    <TextField label={t('script.emotion')} value={b.emotion} onChange={(v) => setBlock(i, { emotion: v })} disabled={!editable} placeholder={t('script.emotion_ph')} />
                  </div>
                  <AreaField label={`${t('script.block_n', { n: i + 1 })}`} value={b.text} onChange={(v) => setBlock(i, { text: v })} disabled={!editable} />
                </div>
                {editable && (
                  <div className="block-tools">
                    <Button size="sm" variant="ghost" iconOnly icon="up" aria-label={t('script.move_up')} disabled={i === 0} onClick={() => move(i, -1)} />
                    <Button size="sm" variant="ghost" iconOnly icon="down" aria-label={t('script.move_down')} disabled={i === d.blocks.length - 1} onClick={() => move(i, 1)} />
                    <Button size="sm" variant="ghost" iconOnly icon="plus" aria-label={t('script.add_below')} onClick={() => setD({ ...d, blocks: [...d.blocks.slice(0, i + 1), blank(), ...d.blocks.slice(i + 1)] })} />
                    <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => setD({ ...d, blocks: d.blocks.filter((_, j) => j !== i) })} />
                  </div>
                )}
              </li>
            ))}
          </ol>
          {editable && (
            <div>
              <Button size="sm" icon="plus" onClick={() => setD({ ...d, blocks: [...d.blocks, blank()] })}>{t('script.add_block')}</Button>
            </div>
          )}
          <TextField label={t('script.cta')} value={d.cta} onChange={(v) => setD({ ...d, cta: v })} disabled={!editable} hint={t('script.cta_hint')} />
        </div>
      </Card>

      {editable && (
        <div className="sticky-actions">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty || d.blocks.every((b) => !b.text.trim())} onClick={doSave}>
            {t('common.save')}
          </Button>
          {hasScript && <Button icon="spark" busy={rewriteBusy} onClick={rewrite}>{t('script.rewrite')}</Button>}
          {dirty && <span className="small muted">{t('prof.unsaved')}</span>}
        </div>
      )}
    </div>
  )
}
