import type { ReactNode } from 'react'

// Small inline icon set (24x24 stroke icons). No icon library on purpose.
const ICONS: Record<string, ReactNode> = {
  home: <path d="M3 11l9-8 9 8M5 10v10h14V10M10 20v-6h4v6" />,
  pages: <path d="M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6" />,
  monitor: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  system: <path d="M6 6h12v12H6zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />,
  settings: (
    <>
      <path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" />
      <circle cx="15" cy="6" r="2" />
      <circle cx="9" cy="12" r="2" />
      <circle cx="17" cy="18" r="2" />
    </>
  ),
  publish: <path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  plus: <path d="M12 5v14M5 12h14" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  up: <path d="M6 15l6-6 6 6" />,
  down: <path d="M6 9l6 6 6-6" />,
  check: <path d="M5 12l5 5 9-10" />,
  alert: <path d="M12 3l10 18H2zM12 10v5M12 18h.01" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7.5h.01" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
  moon: <path d="M20 14a8 8 0 1 1-10-10 6.5 6.5 0 0 0 10 10z" />,
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c3.5 3.5 3.5 14.5 0 18M12 3c-3.5 3.5-3.5 14.5 0 18" />
    </>
  ),
  play: <path d="M7 4l13 8-13 8z" />,
  refresh: <path d="M20 11a8 8 0 1 0-2.3 6M20 4v7h-7" />,
  download: <path d="M12 3v12M7 10l5 5 5-5M4 20h16" />,
  external: <path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" />,
  prev: <path d="M15 6l-6 6 6 6" />,
  next: <path d="M9 6l6 6-6 6" />,
  spark: <path d="M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2zM19 3v4M17 5h4" />,
  edit: <path d="M4 20h4L19 9l-4-4L4 16zM13 7l4 4" />,
  save: <path d="M5 3h12l3 3v15H5zM8 3v6h8V3M8 21v-7h8v7" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c0-3.5 3-6 6.5-6s6.5 2.5 6.5 6M16 4.8a3.5 3.5 0 0 1 0 6.4M18.5 14.3c2 .8 3 2.7 3 5.7" />
    </>
  ),
  film: <path d="M4 4h16v16H4zM8 4v16M16 4v16M4 9h4M4 15h4M16 9h4M16 15h4" />,
  layers: <path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5" />,
  book: <path d="M5 4h9a4 4 0 0 1 4 4v12H9a4 4 0 0 1-4-4zM5 16a4 4 0 0 1 4-4h9" />,
  copy: <path d="M9 9h11v11H9zM5 15V4h11" />,
  stop: <path d="M6 6h12v12H6z" />,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />,
  star: <path d="M12 3l2.7 5.8 6.3.7-4.7 4.3 1.3 6.2L12 17l-5.6 3 1.3-6.2L3 9.5l6.3-.7z" />,
  palette: (
    <>
      <path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 1.4-2.2-.6-1.2.1-2.3 1.4-2.3H17a4 4 0 0 0 4-4c0-5-4-9.5-9-9.5z" />
      <path d="M7.5 11h.01M10 7.5h.01M14.5 7.5h.01M17 11h.01" />
    </>
  ),
  mic: <path d="M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3" />,
  image: <path d="M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9.5h.01" />,
  merge: <path d="M6 4v5a6 6 0 0 0 6 6h0a6 6 0 0 1 6 6M18 4v5a6 6 0 0 1-6 6M12 15v6" />,
  flag: <path d="M5 21V4M5 4h11l-2 4 2 4H5" />,
  lib: <path d="M4 4h4v16H4zM10 4h4v16h-4zM16.5 5l3.5 1-4 14.5-3.5-1z" />,
  link: <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1" />,
}

export type IconName = keyof typeof ICONS

export function Icon({ name, className, size }: { name: IconName; className?: string; size?: number }) {
  return (
    <svg
      className={'icon-svg' + (className ? ' ' + className : '')}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      style={size ? { width: size, height: size } : undefined}
    >
      {ICONS[name]}
    </svg>
  )
}
