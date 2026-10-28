import type { ComponentType } from 'react'
import type { IconName } from '../components/Icon'
import Rigs from './Rigs'
import Voices from './Voices'
import Workers from './Workers'

/**
 * Every Studio screen. The hub tiles and the routes (routes.tsx) are generated from this list.
 * To switch on a screen that is "coming in the next step": set `Component` (and its texts `title.<key>` / `desc.<key>` exist in
 * i18n.ts already) - nothing else changes.
 */
export interface StudioScreen {
  key: 'workers' | 'voices' | 'rigs' | 'comparison' | 'retake' | 'scheduler' | 'publishing' | 'notifications'
  path: string
  icon: IconName
  Component: ComponentType | null
}

export const STUDIO_SCREENS: StudioScreen[] = [
  { key: 'workers', path: 'workers', icon: 'system', Component: Workers },
  { key: 'voices', path: 'voices', icon: 'play', Component: Voices },
  { key: 'rigs', path: 'rigs', icon: 'users', Component: Rigs },
  { key: 'comparison', path: 'comparison', icon: 'layers', Component: null },
  { key: 'retake', path: 'retake', icon: 'film', Component: null },
  { key: 'scheduler', path: 'scheduler', icon: 'clock', Component: null },
  { key: 'publishing', path: 'publishing', icon: 'publish', Component: null },
  { key: 'notifications', path: 'notifications', icon: 'info', Component: null },
]
