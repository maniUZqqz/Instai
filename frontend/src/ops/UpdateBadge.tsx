import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, errorText } from '../api/client'
import { useChoose, useToast } from '../components/feedback'
import { Modal } from '../components/feedback'
import { Spinner } from '../components/ui'
import { Icon } from '../components/Icon'
import { useI18n } from '../i18n'

interface UpdateStatus {
  available: boolean
  current: string
  latest: string
  checked_at: string | null
  error: string
  disabled: boolean
  running_jobs: number
  applying: boolean
}

/**
 * «نسخهٔ تازه آماده است»: shown in the top bar only when GitHub has a newer InstAI (GET /api/update/status, remembered for six hours by the
 * server). One click, after one question, stops the program, installs the update and starts it again (a detached helper, scripts/apply_update.py);
 * this page waits and reloads itself when the new version answers. Nothing is shown when there is nothing to do or GitHub cannot be reached.
 * Layout (audit round ia_regress): the long sentence made every page scroll sideways on a phone (scrollWidth 565 at 390 px). The label is hidden under 760 px
 * (the button keeps its icon, the version and the full text in `title` / `aria-label`), the version too under 560 px, and the button may shrink (`.upd-badge` in styles.css).
 */
export function UpdateBadge() {
  const { t } = useI18n()
  const choose = useChoose()
  const toast = useToast()
  const [st, setSt] = useState<UpdateStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [slow, setSlow] = useState(false)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    const load = () => api.get<UpdateStatus>('/update/status').then((s) => alive.current && setSt(s)).catch(() => undefined)
    load()
    const id = window.setInterval(load, 30 * 60 * 1000)
    return () => {
      alive.current = false
      window.clearInterval(id)
    }
  }, [])

  // after "apply": wait for the server to go away and come back (with the new version), then reload the page
  useEffect(() => {
    if (!restarting) return
    let sawDown = false
    const started = Date.now()
    const id = window.setInterval(async () => {
      try {
        const r = await fetch('/api/health', { cache: 'no-store' })
        if (r.ok && sawDown) {
          window.clearInterval(id)
          window.location.reload()
        }
      } catch {
        sawDown = true
      }
      if (Date.now() - started > 10 * 60 * 1000) setSlow(true)
    }, 3000)
    return () => window.clearInterval(id)
  }, [restarting])

  if (!st || !st.available || st.disabled) return null
  const go = async () => {
    const jobs = st.running_jobs
    const c = await choose({
      title: t('upd.title'),
      message: t('upd.confirm', { v: st.latest || '' }) + (jobs ? ' ' + t('upd.confirm_jobs', { n: jobs }) : ''),
      confirmLabel: t('upd.go'),
    })
    if (c !== 'yes') return
    setBusy(true)
    try {
      await api.post('/update/apply', { force: jobs > 0 })
      setRestarting(true)
    } catch (e) {
      toast.err(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button type="button" className="btn sm primary nowrap upd-badge" onClick={go} disabled={busy || restarting} title={t('upd.badge') + ' — ' + t('upd.title')} aria-label={t('upd.badge') + ' — ' + t('upd.title')} data-testid="update-badge">
        <Icon name="download" />
        <span className="upd-badge-text">{t('upd.badge')}</span>
        {st.latest && <span className="small upd-badge-ver" dir="ltr">v{st.latest}</span>}
      </button>
      {restarting && createPortal(
        <Modal title={t('upd.progress')} onClose={() => undefined}>
          <div className="stack">
            <Spinner label={t('upd.progress_text')} />
            {slow && <p className="small muted">{t('upd.stuck')}</p>}
            <p className="small muted" dir="ltr">v{st.current} → v{st.latest}</p>
          </div>
        </Modal>,
        document.body,
      )}
    </>
  )
}
