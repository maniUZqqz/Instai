import type { ComponentType } from 'react'
import type { IconName } from '../components/Icon'
import Automation from './Automation'
import Compare from './Compare'
import Consistency from './Consistency'
import Mix from './Mix'
import Notifications from './Notifications'
import Retake from './Retake'
import Rigs from './Rigs'
import Voices from './Voices'
import Workers from './Workers'

/**
 * Every Production lab screen. The hub tiles and the routes (routes.tsx) are generated from this list.
 * To add a screen: add a line here and its texts `title.<key>` / `desc.<key>` in i18n2.ts. To switch one off set `Component: null`
 * (its tile then shows as "next step").
 */
export interface LabScreen {
  key: 'workers' | 'voices' | 'rigs' | 'compare' | 'retake' | 'mix' | 'automation' | 'consistency' | 'notifications'
  path: string
  icon: IconName
  Component: ComponentType | null
}

export const LAB_SCREENS: LabScreen[] = [
  { key: 'workers', path: 'workers', icon: 'system', Component: Workers },
  { key: 'voices', path: 'voices', icon: 'play', Component: Voices },
  { key: 'rigs', path: 'rigs', icon: 'users', Component: Rigs },
  { key: 'compare', path: 'compare', icon: 'layers', Component: Compare },
  { key: 'retake', path: 'retake', icon: 'film', Component: Retake },
  { key: 'mix', path: 'mix', icon: 'book', Component: Mix },
  { key: 'automation', path: 'automation', icon: 'clock', Component: Automation },
  { key: 'consistency', path: 'consistency', icon: 'spark', Component: Consistency },
  { key: 'notifications', path: 'notifications', icon: 'info', Component: Notifications },
]
