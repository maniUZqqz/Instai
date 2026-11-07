import { useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import type { VersionInfo } from '../ops/types'

/**
 * The version of InstAI in the corner of EVERY screen (studio, /lab, the not-found page): one small pill like "v0.6.0".
 * Rendered once in App.tsx outside <Routes>, so no screen can forget it. A click opens "What is new" in a NEW tab (an unsaved form on
 * the current screen must not be lost). The number comes from the VERSION file through /api/version; asked once per page load, remembered
 * for ten minutes in sessionStorage. If the server cannot be reached nothing is shown (the page itself keeps working).
 */
const KEY = 'instai.version.v1'
const TTL = 10 * 60 * 1000
let memory: VersionInfo | null = null
let inflight: Promise<VersionInfo | null> | null = null

function stored(): VersionInfo | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as { at?: number; info?: VersionInfo }
    return typeof s.at === 'number' && Date.now() - s.at < TTL && s.info?.version ? s.info : null
  } catch {
    return null
  }
}

export function loadVersion(): Promise<VersionInfo | null> {
  if (memory) return Promise.resolve(memory)
  const s = stored()
  if (s) {
    memory = s
    return Promise.resolve(s)
  }
  if (!inflight) {
    inflight = fetch('/api/version', { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? (r.json() as Promise<VersionInfo>) : null))
      .then((info) => {
        if (info?.version) {
          memory = info
          try {
            sessionStorage.setItem(KEY, JSON.stringify({ at: Date.now(), info }))
          } catch {
            /* storage blocked: only a cache */
          }
          return info
        }
        return null
      })
      .catch(() => null)
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

export function VersionBadge() {
  const { t } = useI18n()
  const [info, setInfo] = useState<VersionInfo | null>(memory)
  useEffect(() => {
    let alive = true
    loadVersion().then((v) => alive && v && setInfo(v))
    return () => {
      alive = false
    }
  }, [])
  if (!info) return null
  return (
    <a
      className="version-badge"
      href="/whats-new"
      target="_blank"
      rel="noopener noreferrer"
      title={t('ops.version.tip', { v: info.version, c: info.commit || '—' })}
      aria-label={t('ops.version.aria', { v: info.version })}
      data-testid="version-badge"
      dir="ltr"
    >
      v{info.version}
    </a>
  )
}
