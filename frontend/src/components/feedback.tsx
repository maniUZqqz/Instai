import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useI18n } from '../i18n'
import { Icon } from './Icon'

// ---------------------------------------------------------------- modal
export function Modal({ title, onClose, children, actions, wide }: { title: string; onClose: () => void; children: ReactNode; actions?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    const first = ref.current?.querySelector<HTMLElement>('input, textarea, select, button.primary, button.danger, button')
    ;(first ?? ref.current)?.focus()
    return () => prev?.focus?.()
  }, [])
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    } else if (e.key === 'Tab' && ref.current) {
      const f = Array.from(ref.current.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled), select, textarea')).filter((x) => x.offsetParent !== null)
      if (!f.length) return
      const first = f[0]
      const last = f[f.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
  }
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={'modal' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-label={title} ref={ref} tabIndex={-1} onKeyDown={onKey}>
        <h2 style={{ marginBlockEnd: '0.75rem' }}>{title}</h2>
        {children}
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- toast + confirm
type ToastKind = 'info' | 'ok' | 'err'
interface ToastItem {
  id: number
  kind: ToastKind
  text: string
}
interface ConfirmOpts {
  title?: string
  message: ReactNode
  confirmLabel?: string
  danger?: boolean
}
interface Ctx {
  push: (kind: ToastKind, text: string) => void
  confirm: (o: ConfirmOpts) => Promise<boolean>
}
const FeedbackCtx = createContext<Ctx | null>(null)

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [dlg, setDlg] = useState<(ConfirmOpts & { resolve: (v: boolean) => void }) | null>(null)
  const seq = useRef(0)
  const push = useCallback((kind: ToastKind, text: string) => {
    const id = ++seq.current
    setToasts((l) => [...l.slice(-3), { id, kind, text }])
    window.setTimeout(() => setToasts((l) => l.filter((x) => x.id !== id)), kind === 'err' ? 9000 : 4000)
  }, [])
  const confirm = useCallback((o: ConfirmOpts) => new Promise<boolean>((resolve) => setDlg({ ...o, resolve })), [])
  const value = useMemo(() => ({ push, confirm }), [push, confirm])
  const close = (v: boolean) => {
    dlg?.resolve(v)
    setDlg(null)
  }
  return (
    <FeedbackCtx.Provider value={value}>
      {children}
      <div className="toast-wrap" aria-live="polite">
        {toasts.map((x) => (
          <div key={x.id} className={'toast ' + x.kind} role={x.kind === 'err' ? 'alert' : 'status'}>
            <Icon name={x.kind === 'err' ? 'alert' : x.kind === 'ok' ? 'check' : 'info'} />
            <span>{x.text}</span>
          </div>
        ))}
      </div>
      {dlg && (
        <Modal
          title={dlg.title ?? t('confirm.title')}
          onClose={() => close(false)}
          actions={
            <>
              <button className="btn" onClick={() => close(false)}>
                {t('common.cancel')}
              </button>
              <button className={'btn ' + (dlg.danger ? 'danger solid' : 'primary')} onClick={() => close(true)}>
                {dlg.confirmLabel ?? t('common.confirm')}
              </button>
            </>
          }
        >
          <div>{dlg.message}</div>
        </Modal>
      )}
    </FeedbackCtx.Provider>
  )
}

function useFeedback(): Ctx {
  const c = useContext(FeedbackCtx)
  if (!c) throw new Error('FeedbackProvider missing')
  return c
}

export function useToast() {
  const { push } = useFeedback()
  return useMemo(() => ({ info: (s: string) => push('info', s), ok: (s: string) => push('ok', s), err: (s: string) => push('err', s) }), [push])
}

export function useConfirm() {
  return useFeedback().confirm
}
