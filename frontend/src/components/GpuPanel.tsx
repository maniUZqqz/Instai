import { useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { GpuCheck, GpuCheckItem, GpuLevel, GpuLive, GpuVerdict, LoadedModel } from '../api/types'
import { useAction, useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { Badge, Button, Card, Notice, Skeleton, type Tone } from './ui'

type Four = 'ok' | 'warn' | 'err' | 'info'

const LEVEL_TONE: Record<GpuLevel, Four> = { ok: 'ok', warn: 'warn', bad: 'err', idle: 'info', none: 'warn' }
const PLACEMENT_TONE: Record<LoadedModel['placement'], Four> = { gpu: 'ok', mixed: 'warn', cpu: 'err' }
const CHECK_TONE: Record<GpuCheckItem['level'], Four> = { ok: 'ok', warn: 'warn', bad: 'err', info: 'info' }

/** A horizontal meter (the `gpu-bar` look); `frac` is 0..1. */
function Bar({ frac, tone, label }: { frac: number; tone?: 'ok' | 'warn' | 'err' | 'hot'; label: string }) {
  const pct = Math.max(0, Math.min(1, Number.isFinite(frac) ? frac : 0)) * 100
  return (
    <div className={'gpu-bar' + (tone ? ' ' + tone : '')} role="img" aria-label={label}>
      <i style={{ width: pct + '%' }} />
    </div>
  )
}

function VerdictBanner({ v, big }: { v: GpuVerdict; big?: boolean }) {
  const { tr, lang } = useI18n()
  const text = (lang === 'en' ? v.text_en : v.text_fa) || ''
  const label = tr('gpu.level.' + v.level, '')
  return (
    <Notice tone={LEVEL_TONE[v.level] ?? 'info'} role="status">
      {label && <div className="strong" style={big ? { fontSize: '1.2rem' } : undefined}>{label}</div>}
      {text && <div style={big ? { marginBlockStart: '0.25rem' } : undefined}>{text}</div>}
    </Notice>
  )
}

/** Live view of the graphics card and of what runs on it (polled every 2.5 s while mounted). */
export function GpuPanel({ compact, extra }: { compact?: boolean; extra?: ReactNode }) {
  const { t, f } = useI18n()
  const q = useQuery<GpuLive>('/gpu/live', { interval: 2500 })
  const d = q.data
  return (
    <Card title={t('gpu.panel_title')} actions={d ? <span className="small muted">{f.time(d.at)}</span> : undefined}>
      {!d ? (
        q.error ? <Notice tone="warn">{t('gpu.live_error')}</Notice> : <Skeleton lines={4} />
      ) : (
        <div className="stack">
          <VerdictBanner v={d.verdict} />
          {extra}
          {!d.gpu && <Notice tone="warn">{t('gpu.no_nvidia')}</Notice>}
          {d.gpu && <GpuBlock gpu={d.gpu} />}
          <OllamaBlock o={d.ollama} />
          <ComfyBlock c={d.comfy} />
          {!compact && <div className="small muted">{t('gpu.tm_hint')}</div>}
          {!compact && <DeepCheck />}
        </div>
      )}
    </Card>
  )
}

function GpuBlock({ gpu }: { gpu: NonNullable<GpuLive['gpu']> }) {
  const { t, f } = useI18n()
  const util = (gpu.utilization ?? 0) / 100
  const frac = gpu.total_mb ? gpu.used_mb / gpu.total_mb : 0
  return (
    <div className="stack-sm">
      <div className="row between">
        <span className="strong ltr">{gpu.name}</span>
        <span className="small muted">
          {t('mon.driver')}: <span className="ltr">{gpu.driver}</span> · {t('mon.temp')}: {f.num(gpu.temperature)}°
        </span>
      </div>
      <div className="row between small">
        <span>{t('gpu.util')}</span>
        <span className="strong">{f.percent(util)}</span>
      </div>
      <Bar frac={util} label={`${t('gpu.util')}: ${f.percent(util)}`} />
      <div className="row between small">
        <span>{t('gpu.vram')}</span>
        <span>
          {f.mb(gpu.used_mb)} / {f.mb(gpu.total_mb)} · {t('gpu.free_n', { mb: f.mb(gpu.free_mb) })}
        </span>
      </div>
      <Bar frac={frac} tone={frac > 0.85 ? 'hot' : undefined} label={`${t('gpu.vram')}: ${f.mb(gpu.used_mb)} / ${f.mb(gpu.total_mb)}`} />
      {gpu.processes.length > 0 && (
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>{t('gpu.procs_n', { n: gpu.processes.length })}</summary>
          <ul className="small" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
            {gpu.processes.map((p) => (
              <li key={p.pid} className="ltr">{p.name} — {f.mb(p.used_mb)}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function OllamaBlock({ o }: { o: GpuLive['ollama'] }) {
  const { t, lang } = useI18n()
  const note = (lang === 'en' ? o.note_en : o.note_fa) || ''
  return (
    <div className="card flat stack-sm">
      <div className="row between">
        <span className="strong">{t('gpu.ollama_title')}</span>
        <Badge tone={o.up ? 'ok' : 'err'}>{o.up ? t('gpu.up') : t('gpu.down')}</Badge>
      </div>
      {!o.up ? (
        !note && <div className="small muted">{t('gpu.ollama_down')}</div>
      ) : o.loaded.length === 0 ? (
        <div className="small muted">{t('gpu.ollama_none')}</div>
      ) : (
        o.loaded.map((m) => <LoadedRow key={m.name} m={m} />)
      )}
      {note && <div className="small">{note}</div>}
    </div>
  )
}

function LoadedRow({ m }: { m: LoadedModel }) {
  const { t, f } = useI18n()
  const tone = PLACEMENT_TONE[m.placement] ?? 'info'
  const pct = Math.round(m.gpu_pct)
  return (
    <div className="stack-sm">
      <div className="row between nw">
        <span className="strong ltr mono">{m.name}</span>
        <Badge tone={tone}>{t(('gpu.placement.' + m.placement) as 'gpu.placement.gpu')}</Badge>
      </div>
      <Bar frac={m.gpu_pct / 100} tone={tone === 'info' ? undefined : tone} label={t('gpu.pct_on_gpu', { n: pct })} />
      <div className="small muted">
        {[
          t('gpu.pct_on_gpu', { n: pct }),
          t('gpu.in_vram', { mb: f.mb(m.vram_mb) }),
          t('gpu.model_size', { mb: f.mb(m.size_mb) }),
          m.context ? t('gpu.context', { n: m.context }) : '',
          m.expires && f.time(m.expires) !== '—' ? t('gpu.expires', { t: f.time(m.expires) }) : '',
        ].filter(Boolean).join(' · ')}
      </div>
    </div>
  )
}

function ComfyBlock({ c }: { c: GpuLive['comfy'] }) {
  const { t, f, lang } = useI18n()
  const note = (lang === 'en' ? c.note_en : c.note_fa) || ''
  return (
    <div className="card flat stack-sm">
      <div className="row between">
        <span className="strong">{t('gpu.comfy_title')}</span>
        <Badge tone={c.up ? 'ok' : 'err'}>{c.up ? t('gpu.up') : t('gpu.down')}</Badge>
      </div>
      {c.up && (
        <dl className="kv small">
          <dt>{t('gpu.comfy_device')}</dt>
          <dd>
            {c.device ? <Badge tone={c.device === 'cuda' ? 'ok' : 'err'}>{c.device === 'cuda' ? t('gpu.dev_cuda') : t('gpu.dev_cpu')}</Badge> : '—'}
            {c.device_name ? <> <span className="ltr">{c.device_name}</span></> : null}
          </dd>
          {c.torch && (
            <>
              <dt>{t('gpu.torch')}</dt>
              <dd className="ltr mono">{c.torch}</dd>
            </>
          )}
          {c.vram_total_mb != null && (
            <>
              <dt>{t('gpu.comfy_vram')}</dt>
              <dd>{t('gpu.comfy_vram_val', { free: f.mb(c.vram_free_mb), total: f.mb(c.vram_total_mb) })}</dd>
            </>
          )}
        </dl>
      )}
      {c.cpu_flag && <Notice tone="err">{t('gpu.cpu_flag')}</Notice>}
      {note && <div className="small">{note}</div>}
    </div>
  )
}

/** The button that runs the slow "why is the GPU not used" check and shows its result below. */
function DeepCheck() {
  const { t } = useI18n()
  const act = useAction()
  const [result, setResult] = useState<GpuCheck | null>(null)
  const run = async () => {
    const r = await act.run(() => api.post<GpuCheck>('/gpu/check', {}))
    if (r) setResult(r)
  }
  return (
    <div className="stack-sm">
      <div className="row">
        <Button icon="monitor" busy={act.busy} onClick={run} wrap>
          {act.busy ? t('gpu.deep_checking') : t('gpu.deep_check')}
        </Button>
      </div>
      {result && <GpuCheckView check={result} />}
    </div>
  )
}

/** Result of the deep check: the verdict (big, coloured), then one row per finding with its fix. */
export function GpuCheckView({ check }: { check: GpuCheck }) {
  const { t, tr, f, lang } = useI18n()
  const pick = (fa: string, en: string) => (lang === 'en' ? en : fa) || ''
  return (
    <div className="stack-sm">
      <VerdictBanner v={check.verdict} big />
      {check.checks.length === 0 ? (
        <div className="small muted">{t('gpu.check_none')}</div>
      ) : (
        <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {check.checks.map((c) => {
            const tone: Tone = CHECK_TONE[c.level] ?? 'neutral'
            const detail = pick(c.detail_fa, c.detail_en)
            const fix = pick(c.fix_fa, c.fix_en)
            return (
              <li key={c.id} className="card flat">
                <div className="row nw start">
                  <span className={'dot ' + (tone === 'info' ? '' : tone)} style={{ marginBlockStart: '0.6rem' }} aria-hidden="true" />
                  <div className="grow stack-sm">
                    <div className="row">
                      <span className="strong">{pick(c.title_fa, c.title_en)}</span>
                      <Badge tone={tone}>{tr('gpu.check_level.' + c.level, c.level)}</Badge>
                    </div>
                    {detail && <div className="small pre">{detail}</div>}
                    {fix && (
                      <div className="small pre">
                        <span className="strong">{t('gpu.check_fix')}:</span> {fix}
                      </div>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <div className="small muted">{t('gpu.check_took', { n: f.num(check.took, 1) })}</div>
    </div>
  )
}
