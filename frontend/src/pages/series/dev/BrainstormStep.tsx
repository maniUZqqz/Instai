import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../api/client'
import type { Idea } from '../../../api/types'
import { useConfirm } from '../../../components/feedback'
import { Icon } from '../../../components/Icon'
import { AreaField, Badge, Button, Card, CheckField, Empty, NumberField, Segmented, TextField } from '../../../components/ui'
import { useAction, useJobRunner } from '../../../hooks'
import { useI18n } from '../../../i18n'
import { LENS_FIELDS, LocalJob, StepFrame, type StepProps } from './common'

type Filter = 'active' | 'approved' | 'rejected' | 'all'

export function BrainstormStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, step, reload } = p
  const board = step.params.board ?? step.key
  const lens = step.params.lens ?? 'series_concept'
  const ideas = dev.ideas[board] ?? []
  const confirm = useConfirm()
  const act = useAction()
  const [filter, setFilter] = useState<Filter>('active')
  const [sel, setSel] = useState<number[]>([])
  const [count, setCount] = useState<number | null>(step.params.count ?? 6)
  const [instruction, setInstruction] = useState('')
  const [adding, setAdding] = useState(false)
  const runner = useJobRunner({ onSucceeded: () => reload() })
  const busy = runner.starting || runner.busy
  const shown = useMemo(() => ideas.filter((i) => (filter === 'all' ? true : filter === 'active' ? i.status !== 'rejected' : i.status === filter)), [ideas, filter])
  const counts = { active: ideas.filter((i) => i.status !== 'rejected').length, approved: ideas.filter((i) => i.status === 'approved').length, rejected: ideas.filter((i) => i.status === 'rejected').length, all: ideas.length }
  const generate = (moreLike: number[] = []) => runner.start(() => api.post(`/series/${dev.series.id}/ideas/generate`, { board, count: count ?? 6, instruction, more_like: moreLike, language: lang }))
  const merge = async (ai: boolean) => {
    if (ai) {
      await runner.start(() => api.post(`/series/${dev.series.id}/ideas/merge`, { ids: sel, ai: true, instruction, language: lang }))
    } else {
      const r = await act.run(() => api.post(`/series/${dev.series.id}/ideas/merge`, { ids: sel, language: lang }), { success: t('idea.merged') })
      if (r) reload()
    }
    setSel([])
  }
  const approvedN = counts.approved
  return (
    <StepFrame {...p}>
      <Card title={t('idea.board')}>
        <div className="stack">
          <p className="small muted">{t(('lens.' + lens) as 'lens.divergence')}</p>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <NumberField label={t('idea.count')} min={1} max={12} value={count} onChange={setCount} className="narrow" />
            <TextField className="grow" label={t('idea.instruction')} value={instruction} onChange={setInstruction} placeholder={t('idea.instruction_ph')} />
            <Button variant="primary" icon="spark" busy={busy} onClick={() => generate()}>{ideas.length ? t('idea.more') : t('idea.generate')}</Button>
          </div>
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
          <div className="row">
            <Button icon="plus" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>{t('idea.add_mine')}</Button>
            {sel.length >= 2 && (
              <>
                <Button icon="merge" busy={act.busy} onClick={() => merge(false)}>{t('idea.merge_hand', { n: sel.length })}</Button>
                <Button icon="spark" busy={busy} onClick={() => merge(true)}>{t('idea.merge_ai', { n: sel.length })}</Button>
              </>
            )}
            {sel.length > 0 && <Button variant="ghost" onClick={() => setSel([])}>{t('idea.clear_sel')}</Button>}
          </div>
        </div>
      </Card>

      {adding && <AddIdea {...p} board={board} lens={lens} onDone={() => { setAdding(false); reload() }} />}

      <div className="row between">
        <Segmented<Filter> label={t('idea.filter')} value={filter} onChange={setFilter}
          options={(['active', 'approved', 'rejected', 'all'] as Filter[]).map((k) => ({ key: k, label: `${t(('idea.f_' + k) as 'idea.f_all')} (${counts[k]})` }))} />
        <span className="small muted">{t('idea.approved_n', { n: approvedN })}</span>
      </div>

      {ideas.length === 0 && <Empty icon="spark" title={t('idea.empty')} text={t('idea.empty_text')} />}
      <div className="grid-auto idea-grid">
        {shown.map((i) => (
          <IdeaCard key={i.id + ':' + i.status + ':' + i.rating + ':' + i.title + i.logline} idea={i} lens={lens} selected={sel.includes(i.id)} busy={busy}
            onSelect={(on) => setSel(on ? [...sel, i.id] : sel.filter((x) => x !== i.id))} reload={reload}
            onMore={() => generate([i.id])}
            onRefine={(ins) => runner.start(() => api.post(`/ideas/${i.id}/refine`, { instruction: ins, language: lang }))}
            parent={ideas.find((x) => x.id === i.parent)}
            onDelete={async () => { if (await confirm({ message: t('idea.delete_confirm'), danger: true, confirmLabel: t('common.delete') })) await act.run(async () => { await api.del(`/ideas/${i.id}`); reload() }) }} />
        ))}
      </div>
    </StepFrame>
  )
}

function AddIdea({ dev, board, lens, onDone }: StepProps & { board: string; lens: string; onDone: () => void }) {
  const { t, tr, lang } = useI18n()
  const act = useAction()
  const [d, setD] = useState({ title: '', logline: '', why: '', details: {} as Record<string, string> })
  const save = async () => {
    const r = await act.run(() => api.post(`/series/${dev.series.id}/ideas`, { board, ...d, language: lang }), { success: t('idea.added') })
    if (r) onDone()
  }
  return (
    <Card title={t('idea.add_mine')}>
      <div className="stack">
        <TextField label={t('idea.title')} required value={d.title} onChange={(v) => setD({ ...d, title: v })} autoFocus />
        <AreaField label={t('idea.logline')} compact value={d.logline} onChange={(v) => setD({ ...d, logline: v })} />
        <AreaField label={t('idea.why')} compact value={d.why} onChange={(v) => setD({ ...d, why: v })} />
        <div className="grid-2">
          {(LENS_FIELDS[lens] ?? []).map((k) => (
            <AreaField key={k} compact label={tr('idea.f.' + k, k)} value={d.details[k] ?? ''} onChange={(v) => setD({ ...d, details: { ...d.details, [k]: v } })} />
          ))}
        </div>
        <div className="row">
          <Button variant="primary" icon="check" busy={act.busy} disabled={!d.title.trim()} onClick={save}>{t('common.add')}</Button>
          <Button onClick={onDone}>{t('common.cancel')}</Button>
        </div>
      </div>
    </Card>
  )
}

function Stars({ value, onChange, disabled }: { value: number; onChange: (n: number) => void; disabled?: boolean }) {
  const { t } = useI18n()
  return (
    <span className="stars" role="group" aria-label={t('idea.rating')}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" className={'star' + (n <= value ? ' on' : '')} disabled={disabled} aria-pressed={n <= value} aria-label={t('idea.rate_n', { n })} onClick={() => onChange(n === value ? 0 : n)}>
          <Icon name="star" />
        </button>
      ))}
    </span>
  )
}

function IdeaCard({ idea, lens, selected, onSelect, reload, busy, onMore, onRefine, onDelete, parent }: {
  idea: Idea
  lens: string
  selected: boolean
  onSelect: (on: boolean) => void
  reload: () => void
  busy: boolean
  onMore: () => void
  onRefine: (instruction: string) => void
  onDelete: () => void
  parent?: Idea
}) {
  const { t, tr } = useI18n()
  const act = useAction()
  const [edit, setEdit] = useState(false)
  const [refine, setRefine] = useState(false)
  const [ins, setIns] = useState('')
  const [d, setD] = useState({ title: idea.title, logline: idea.logline, why: idea.why, details: idea.details })
  useEffect(() => setD({ title: idea.title, logline: idea.logline, why: idea.why, details: idea.details }), [idea.title, idea.logline, idea.why, idea.details])
  const setStatus = (status: string) => act.run(async () => { await api.post(`/ideas/${idea.id}/status`, { status }); reload() })
  const rate = (rating: number) => act.run(async () => { await api.post(`/ideas/${idea.id}/rate`, { rating }); reload() })
  const save = async () => {
    const r = await act.run(async () => { await api.patch(`/ideas/${idea.id}`, d); return true }, { success: t('common.saved') })
    if (r) { setEdit(false); reload() }
  }
  const keys = Array.from(new Set([...(LENS_FIELDS[lens] ?? []), ...Object.keys(idea.details)]))
  const tone = idea.status === 'approved' ? 'ok' : idea.status === 'rejected' ? 'err' : idea.status === 'liked' ? 'info' : 'neutral'
  return (
    <article className={'card idea stack-sm' + (idea.status === 'approved' ? ' approved' : '') + (idea.status === 'rejected' ? ' rejected' : '')} aria-label={idea.title}>
      <div className="row between" style={{ flexWrap: 'nowrap' }}>
        <CheckField label={<span className="sr-only">{t('idea.select')}</span>} checked={selected} onChange={onSelect} />
        <div className="row" style={{ gap: '0.25rem' }}>
          <Badge tone={idea.author === 'ai' ? 'primary' : idea.author === 'human' ? 'neutral' : 'info'}>{t(('idea.by_' + idea.author) as 'idea.by_ai')}</Badge>
          {idea.status !== 'proposed' && <Badge tone={tone}>{t(('idea.st_' + idea.status) as 'idea.st_approved')}</Badge>}
        </div>
      </div>
      {edit ? (
        <div className="stack-sm">
          <TextField label={t('idea.title')} value={d.title} onChange={(v) => setD({ ...d, title: v })} />
          <AreaField label={t('idea.logline')} compact value={d.logline} onChange={(v) => setD({ ...d, logline: v })} />
          <AreaField label={t('idea.why')} compact value={d.why} onChange={(v) => setD({ ...d, why: v })} />
          {keys.map((k) => (
            <AreaField key={k} compact label={tr('idea.f.' + k, k)} value={d.details[k] ?? ''} onChange={(v) => setD({ ...d, details: { ...d.details, [k]: v } })} />
          ))}
          <div className="row">
            <Button size="sm" variant="primary" icon="save" busy={act.busy} disabled={!d.title.trim()} onClick={save}>{t('common.save')}</Button>
            <Button size="sm" onClick={() => setEdit(false)}>{t('common.cancel')}</Button>
          </div>
        </div>
      ) : (
        <>
          <h3 className="idea-title">{idea.title}</h3>
          {idea.logline && <p>{idea.logline}</p>}
          {idea.why && <p className="small muted"><strong>{t('idea.why')}:</strong> {idea.why}</p>}
          {Object.keys(idea.details).length > 0 && (
            <dl className="kv small">
              {keys.filter((k) => idea.details[k]).map((k) => (<div key={k} style={{ display: 'contents' }}><dt>{tr('idea.f.' + k, k)}</dt><dd>{idea.details[k]}</dd></div>))}
            </dl>
          )}
          {parent && <p className="small muted">{t('idea.from', { title: parent.title })}</p>}
        </>
      )}
      <Stars value={idea.rating} onChange={rate} disabled={act.busy} />
      <div className="row idea-actions">
        <Button size="sm" variant={idea.status === 'approved' ? 'primary' : 'default'} icon="check" busy={act.busy} onClick={() => setStatus(idea.status === 'approved' ? 'proposed' : 'approved')}>
          {idea.status === 'approved' ? t('idea.unapprove') : t('idea.approve')}
        </Button>
        <Button size="sm" busy={act.busy} onClick={() => setStatus(idea.status === 'liked' ? 'proposed' : 'liked')}>{idea.status === 'liked' ? t('idea.unlike') : t('idea.like')}</Button>
        <Button size="sm" variant={idea.status === 'rejected' ? 'default' : 'ghost'} busy={act.busy} onClick={() => setStatus(idea.status === 'rejected' ? 'proposed' : 'rejected')}>{idea.status === 'rejected' ? t('idea.restore') : t('idea.reject')}</Button>
      </div>
      <div className="row idea-actions">
        <Button size="sm" variant="ghost" icon="edit" onClick={() => setEdit((e) => !e)}>{t('common.edit')}</Button>
        <Button size="sm" variant="ghost" icon="spark" disabled={busy} onClick={() => setRefine((r) => !r)} aria-expanded={refine}>{t('idea.refine')}</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onMore}>{t('idea.like_this')}</Button>
        <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.delete')} onClick={onDelete} />
      </div>
      {refine && (
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <TextField className="grow" label={t('idea.refine_ins')} value={ins} onChange={setIns} placeholder={t('idea.refine_ph')} />
          <Button size="sm" variant="primary" disabled={busy || !ins.trim()} onClick={() => { onRefine(ins); setRefine(false); setIns('') }}>{t('idea.refine_go')}</Button>
        </div>
      )}
    </article>
  )
}
