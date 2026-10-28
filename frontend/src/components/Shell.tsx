import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import type { Job, SettingsPayload } from '../api/types'
import { useQuery } from '../hooks'
import { useI18n } from '../i18n'
import { Icon, type IconName } from './Icon'
import { Link, NavLink, Progress, Button } from './ui'

// ---------------------------------------------------------------- app-wide facts (demo mode)
interface AppCtx {
  demo: boolean | undefined
  refreshDemo: () => void
}
const AppContext = createContext<AppCtx>({ demo: undefined, refreshDemo: () => {} })
export const useApp = () => useContext(AppContext)

// ---------------------------------------------------------------- theme (light / dark / follow the system)
function systemDark() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}
function useTheme() {
  const [explicit, setExplicit] = useState<'light' | 'dark' | null>(() => {
    const a = document.documentElement.getAttribute('data-theme')
    return a === 'light' || a === 'dark' ? a : null
  })
  const effective = explicit ?? (systemDark() ? 'dark' : 'light')
  const toggle = () => {
    const next = effective === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    try {
      localStorage.setItem('instai.theme', next)
    } catch {
      /* storage blocked: stays for this visit */
    }
    setExplicit(next)
  }
  return { effective, toggle }
}

// ---------------------------------------------------------------- job indicator (all queued/running jobs, any screen)
function JobIndicator() {
  const { t, f } = useI18n()
  const q = useQuery<Job[]>('/jobs?status=queued,running&limit=50', { interval: 3000 })
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const loc = useLocation()
  useEffect(() => setOpen(false), [loc.pathname])
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  const jobs = q.data ?? []
  const running = jobs.filter((j) => j.status === 'running')
  const label = jobs.length ? t('shell.jobs_active', { n: jobs.length }) : t('shell.jobs_none')
  return (
    <div className="popover-wrap" ref={ref}>
      <button type="button" className="btn ghost sm" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((o) => !o)} aria-label={label}>
        {jobs.length ? <span className="spinner" aria-hidden="true" /> : <Icon name="monitor" />}
        <span className="nowrap">{jobs.length ? f.num(jobs.length) : ''}</span>
        <span className="sr-only" role="status">{label}</span>
      </button>
      {open && (
        <div className="popover stack-sm">
          <div className="strong">{label}</div>
          {jobs.slice(0, 6).map((j) => (
            <div key={j.id} className="stack-sm">
              <div className="small">{j.title || j.kind}</div>
              <Progress value={j.progress} indeterminate={j.status === 'queued' || j.progress <= 0} label={j.title} />
              {j.waiting_reason && <div className="small muted">{j.waiting_reason}</div>}
            </div>
          ))}
          {jobs.length > 6 && <div className="small muted">+{f.num(jobs.length - 6)}</div>}
          {running.length === 0 && jobs.length > 0 && <div className="small muted">{t('shell.jobs_waiting')}</div>}
          <Link to="/monitor" className="btn sm">
            {t('shell.open_monitor')}
          </Link>
        </div>
      )}
    </div>
  )
}

const NAV: { to: string; key: Parameters<ReturnType<typeof useI18n>['t']>[0]; icon: IconName; end?: boolean }[] = [
  { to: '/', key: 'nav.dashboard', icon: 'home', end: true },
  { to: '/pages', key: 'nav.pages', icon: 'pages' },
  { to: '/monitor', key: 'nav.monitor', icon: 'monitor' },
  { to: '/publishing', key: 'nav.publishing', icon: 'publish' },
  { to: '/system', key: 'nav.system', icon: 'system' },
  { to: '/settings', key: 'nav.settings', icon: 'settings' },
]

export function Shell() {
  const { t, lang, setLang } = useI18n()
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const settings = useQuery<SettingsPayload>('/settings')
  const [demoOverride, setDemoOverride] = useState<boolean | undefined>()
  const refreshDemo = useCallback(() => {
    api
      .get<SettingsPayload>('/settings')
      .then((s) => setDemoOverride(s.demo_mode))
      .catch(() => undefined)
  }, [])
  const demo = demoOverride ?? settings.data?.demo_mode

  useEffect(() => setOpen(false), [loc.pathname])
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [loc.pathname])
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <AppContext.Provider value={{ demo, refreshDemo }}>
      <a href="#main" className="sr-only">
        {t('shell.skip')}
      </a>
      <div className="shell">
        <aside className={'sidebar' + (open ? ' open' : '')} aria-label={t('shell.nav')}>
          <Link to="/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <Icon name="play" size={18} />
            </span>
            InstAI
          </Link>
          <nav className="nav">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
                <Icon name={n.icon} />
                {t(n.key)}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-foot">{t('shell.tagline')}</div>
        </aside>
        <div className={'scrim' + (open ? ' open' : '')} onClick={() => setOpen(false)} aria-hidden="true" />
        <div className="main">
          <header className="topbar">
            <Button className="menu-btn" variant="ghost" iconOnly icon={open ? 'close' : 'menu'} aria-label={t('shell.menu')} aria-expanded={open} onClick={() => setOpen((o) => !o)} />
            <div className="spacer" />
            <JobIndicator />
            <Button variant="ghost" size="sm" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')} aria-label={t('shell.lang_switch')} title={t('shell.lang_switch')}>
              <Icon name="globe" />
              {lang === 'fa' ? 'EN' : 'فارسی'}
            </Button>
            <Button variant="ghost" size="sm" iconOnly icon={theme.effective === 'dark' ? 'sun' : 'moon'} onClick={theme.toggle} aria-label={t(theme.effective === 'dark' ? 'shell.theme_light' : 'shell.theme_dark')} title={t(theme.effective === 'dark' ? 'shell.theme_light' : 'shell.theme_dark')} />
          </header>
          {demo && loc.pathname !== '/' && (
            <div className="banner-demo" role="status">
              <Icon name="alert" />
              <span>{t('shell.demo_banner')}</span>
              <Link to="/settings">{t('shell.demo_link')}</Link>
            </div>
          )}
          <main id="main" className="content" tabIndex={-1}>
            <Outlet />
          </main>
        </div>
      </div>
    </AppContext.Provider>
  )
}
