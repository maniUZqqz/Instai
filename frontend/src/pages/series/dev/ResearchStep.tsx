import { useState } from 'react'
import { api } from '../../../api/client'
import type { ResearchDocT } from '../../../api/types'
import { SourcesPanel } from '../../../components/SourcesPanel'
import { Badge, Button, Card, Empty, Notice, TextField } from '../../../components/ui'
import { useAction, useJobRunner } from '../../../hooks'
import { useI18n } from '../../../i18n'
import { LocalJob, SourceBadges, StepFrame, type StepProps } from './common'

interface CanonContent {
  summary?: string
  characters?: { name: string; role: string; abilities?: string; arc?: string; relationships?: string; source_ids?: number[] }[]
  arcs?: { title: string; summary: string; source_ids?: number[] }[]
  key_events?: { when?: string; event: string; importance?: string; source_ids?: number[] }[]
  world_rules?: { rule: string; source_ids?: number[] }[]
  themes?: string[]
  caveats?: string[]
}

export function ResearchStep(p: StepProps) {
  const { t, lang } = useI18n()
  const { dev, step, reload } = p
  const mode = (step.params.mode as 'canon' | 'topic') ?? 'topic'
  const doc: ResearchDocT | undefined = dev.research[mode]
  const [topic, setTopic] = useState(doc?.content.topic ?? dev.series.title)
  const [version, setVersion] = useState(0)
  const runner = useJobRunner({ onSucceeded: () => { reload(); setVersion((v) => v + 1) } })
  const run = () => runner.start(() => api.post(`/series/${dev.series.id}/research`, { mode, topic, language: lang }))
  const fetchErrors: string[] = doc?.meta?.fetch_errors ?? []
  return (
    <StepFrame {...p}>
      {mode === 'canon' && !dev.source.title && <Notice tone="warn">{t('res.need_source')}</Notice>}
      <Card title={mode === 'canon' ? t('res.canon_title') : t('res.topic_title')}>
        <div className="stack">
          <p className="muted small">{mode === 'canon' ? t('res.canon_intro') : t('res.topic_intro')}</p>
          {mode === 'topic' && <TextField label={t('res.topic')} value={topic} onChange={setTopic} />}
          <div className="row">
            <Button variant="primary" icon="spark" busy={runner.starting || runner.busy} disabled={mode === 'canon' ? !dev.source.title : !topic.trim()} onClick={run}>
              {doc ? t('res.rerun') : t('res.run')}
            </Button>
            {doc && <span className="small muted">{t('res.rerun_note')}</span>}
          </div>
          {runner.job && !runner.succeeded && <LocalJob job={runner.job} offline={runner.offline} />}
          {fetchErrors.length > 0 && (
            <Notice tone="warn">
              <div className="stack-sm">
                <div>{t('res.fetch_errors')}</div>
                <ul className="small ltr" style={{ margin: 0, paddingInlineStart: '1.25rem' }}>{fetchErrors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </div>
            </Notice>
          )}
        </div>
      </Card>
      {doc ? (mode === 'canon' ? <CanonView {...p} doc={doc} /> : <TopicView {...p} doc={doc} />) : <Empty icon="book" title={t('res.empty')} text={t('res.empty_text')} />}
      <Card title={t('res.sources')}>
        <p className="muted small">{t('res.sources_note')}</p>
        <SourcesPanel pageId={dev.series.page} seriesId={dev.series.id} version={version + dev.sources.length} onChanged={reload} />
      </Card>
    </StepFrame>
  )
}

function CanonView({ dev, doc, reload }: StepProps & { doc: ResearchDocT }) {
  const { t } = useI18n()
  const c = doc.content as CanonContent
  const [summary, setSummary] = useState(c.summary ?? '')
  const act = useAction()
  const save = (content: CanonContent) => act.run(async () => { await api.patch(`/research-docs/${doc.id}`, { content }); reload() }, { success: t('common.saved') })
  const drop = (group: keyof CanonContent, i: number) => save({ ...c, [group]: ((c[group] as unknown[]) ?? []).filter((_, j) => j !== i) })
  const del = (group: keyof CanonContent, i: number) => (
    <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => drop(group, i)} />
  )
  return (
    <Card title={t('res.canon_doc')} actions={<Badge tone={doc.status === 'reviewed' ? 'ok' : 'neutral'}>{doc.status === 'reviewed' ? t('res.reviewed') : t('res.draft')}</Badge>}>
      <div className="stack">
        <div className="stack-sm">
          <label className="field-label" htmlFor="canon-summary">{t('res.summary')}</label>
          <textarea id="canon-summary" className="compact" value={summary} onChange={(e) => setSummary(e.target.value)} />
          <div><Button size="sm" icon="save" disabled={summary === (c.summary ?? '')} busy={act.busy} onClick={() => save({ ...c, summary })}>{t('common.save')}</Button></div>
        </div>
        <Group title={t('res.characters')} n={c.characters?.length}>
          {(c.characters ?? []).map((x, i) => (
            <li key={i} className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <div className="stack-sm"><div><span className="strong">{x.name}</span> <span className="muted">· {x.role}</span></div>
                {x.abilities && <div className="small">{t('res.abilities')}: {x.abilities}</div>}
                {x.arc && <div className="small">{t('res.arc')}: {x.arc}</div>}
                <SourceBadges dev={dev} ids={x.source_ids} /></div>
              {del('characters', i)}
            </li>
          ))}
        </Group>
        <Group title={t('res.arcs')} n={c.arcs?.length}>
          {(c.arcs ?? []).map((x, i) => (
            <li key={i} className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <div className="stack-sm"><div className="strong">{x.title}</div><div className="small">{x.summary}</div><SourceBadges dev={dev} ids={x.source_ids} /></div>
              {del('arcs', i)}
            </li>
          ))}
        </Group>
        <Group title={t('res.events')} n={c.key_events?.length}>
          {(c.key_events ?? []).map((x, i) => (
            <li key={i} className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <div className="stack-sm"><div>{x.when && <span className="muted">{x.when}: </span>}{x.event}{x.importance ? <Badge>{x.importance}</Badge> : null}</div><SourceBadges dev={dev} ids={x.source_ids} /></div>
              {del('key_events', i)}
            </li>
          ))}
        </Group>
        <Group title={t('res.rules')} n={c.world_rules?.length}>
          {(c.world_rules ?? []).map((x, i) => (
            <li key={i} className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <div className="stack-sm"><div>{x.rule}</div><SourceBadges dev={dev} ids={x.source_ids} /></div>
              {del('world_rules', i)}
            </li>
          ))}
        </Group>
        {(c.themes?.length ?? 0) > 0 && <div className="row"><span className="strong">{t('res.themes')}:</span>{c.themes!.map((x) => <Badge key={x}>{x}</Badge>)}</div>}
        {(c.caveats?.length ?? 0) > 0 && <Notice tone="warn"><ul style={{ margin: 0, paddingInlineStart: '1.25rem' }}>{c.caveats!.map((x, i) => <li key={i}>{x}</li>)}</ul></Notice>}
        <div className="row">
          <Button icon="check" busy={act.busy} onClick={() => act.run(async () => { await api.patch(`/research-docs/${doc.id}`, { status: doc.status === 'reviewed' ? 'draft' : 'reviewed' }); reload() })}>
            {doc.status === 'reviewed' ? t('res.unreview') : t('res.mark_reviewed')}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function Group({ title, n, children }: { title: string; n?: number; children: React.ReactNode }) {
  return (
    <div className="stack-sm">
      <h3>{title} <span className="muted small">({n ?? 0})</span></h3>
      {(n ?? 0) > 0 && <ul className="plain-list stack-sm">{children}</ul>}
    </div>
  )
}

function TopicView({ dev, doc }: StepProps & { doc: ResearchDocT }) {
  const { t } = useI18n()
  const c = doc.content as { claims?: { claim: string; stance: string; source_ids: number[]; unsupported?: boolean }[]; analogies?: string[]; visual_metaphors?: string[]; caveats?: string[]; unsupported_count?: number }
  return (
    <Card title={t('res.topic_doc')}>
      <div className="stack">
        <p className="small muted">{t('res.topic_doc_note')}</p>
        <ul className="plain-list stack-sm">
          {(c.claims ?? []).map((x, i) => (
            <li key={i} className="stack-sm">
              <div><Badge tone={x.stance === 'established' ? 'ok' : x.stance === 'contested' ? 'warn' : 'neutral'}>{t(('stance.' + x.stance) as 'stance.established')}</Badge> {x.claim}</div>
              <SourceBadges dev={dev} ids={x.source_ids} />
            </li>
          ))}
        </ul>
        {(c.analogies?.length ?? 0) > 0 && <div><strong>{t('res.analogies')}:</strong> {c.analogies!.join(' · ')}</div>}
        {(c.caveats?.length ?? 0) > 0 && <Notice tone="warn">{c.caveats!.join(' · ')}</Notice>}
      </div>
    </Card>
  )
}
