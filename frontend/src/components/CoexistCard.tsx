import { api } from '../api/client'
import { useAction, useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { Badge, Button, Card, Notice, Skeleton } from './ui'

interface Coexist {
  nm_agent: boolean
  nm_agent_pid: number | null
  ports: { port: number; name: string; owner: 'instai' | 'shared' | 'nmarketing'; open: boolean }[]
  vram: { name?: string; total_mb?: number; used_mb?: number; free_mb?: number; apps?: { pid: number; name: string; mb: number | null; who: string }[] }
  ollama_env: { vars: { name: string; recommended: string; current: string | null; ok: boolean }[]; ok: boolean; windows: boolean }
  advice: { id: string; level: string; fa: string; en: string }[]
  release_after_seconds: number
}

interface Applied {
  saved: string[]
  error: string
  restart: { restarted: boolean; reason: string } | null
}

/** One PC, two programs (InstAI and the NMarketing agent): who uses which port, who holds the graphics memory, and the Ollama settings
 *  that keep the model completely on the GPU. */
export function CoexistCard() {
  const { t, lang, f } = useI18n()
  const q = useQuery<Coexist>('/gpu/coexist', { interval: 10000 })
  const act = useAction()
  const d = q.data
  const apply = (restart: boolean) =>
    void act.run(async () => {
      const r = await api.post<Applied>('/gpu/ollama-settings', { restart })
      q.reload()
      return r
    }, { success: restart ? t('gpu.co.env_restarted') : t('gpu.co.env_saved') })
  return (
    <div data-testid="coexist-card"><Card title={t('gpu.co.title')}>
      {!d ? (
        q.error ? <Notice tone="warn">{t('gpu.live_error')}</Notice> : <Skeleton lines={3} />
      ) : (
        <div className="stack">
          <Notice tone="info" icon="info">{d.nm_agent ? t('gpu.co.agent_on') : t('gpu.co.agent_off')}</Notice>
          {d.vram.total_mb ? (
            <div className="stack-sm">
              <div className="strong">{t('gpu.co.vram', { used: f.num(d.vram.used_mb ?? 0), total: f.num(d.vram.total_mb) })}</div>
              {(d.vram.apps ?? []).length > 0 && (
                <div className="small muted ltr" dir="ltr">{t('gpu.co.vram_apps')}: {(d.vram.apps ?? []).map((a) => `${a.name} ${a.mb ?? '?'} MB`).join(' · ')}</div>
              )}
            </div>
          ) : null}
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th colSpan={3}>{t('gpu.co.ports')}</th></tr></thead>
              <tbody>
                {d.ports.map((p) => (
                  <tr key={p.port}>
                    <td className="ltr" dir="ltr">{p.port} · {p.name}</td>
                    <td className="small">{t(('gpu.co.owner_' + p.owner) as 'gpu.co.owner_shared')}</td>
                    <td><Badge tone={p.open ? 'ok' : 'neutral'}>{p.open ? t('gpu.co.port_open') : t('gpu.co.port_closed')}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.advice.filter((a) => a.id !== 'nm_agent' && a.id !== 'ollama_env').map((a) => (
            <Notice key={a.id} tone="warn" icon="info"><span dir="auto">{lang === 'en' ? a.en : a.fa}</span></Notice>
          ))}
          <div className="stack-sm">
            <div className="strong">{t('gpu.co.env_title')}</div>
            <Notice tone={d.ollama_env.ok ? 'ok' : 'warn'} icon={d.ollama_env.ok ? 'check' : 'info'}>{d.ollama_env.ok ? t('gpu.co.env_ok') : t('gpu.co.env_missing')}</Notice>
            <div className="small muted ltr" dir="ltr">{d.ollama_env.vars.map((v) => `${v.name}=${v.current ?? '-'} (${v.recommended})`).join('  ·  ')}</div>
            {d.ollama_env.windows && !d.ollama_env.ok && (
              <div className="row">
                <Button icon="save" busy={act.busy} onClick={() => apply(false)} data-testid="coexist-apply">{t('gpu.co.env_apply')}</Button>
                <Button icon="refresh" busy={act.busy} onClick={() => apply(true)}>{t('gpu.co.env_apply_restart')}</Button>
              </div>
            )}
          </div>
          <p className="small muted">{t('gpu.co.release', { n: d.release_after_seconds })}</p>
        </div>
      )}
    </Card></div>
  )
}
