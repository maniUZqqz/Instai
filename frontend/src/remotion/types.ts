export interface RmStatus {
  ready: boolean
  node: { path: string; version: string; source: string } | null
  packages: boolean
  browser: { path: string; source: string; mode: string } | null
  state: 'idle' | 'running' | 'ready' | 'error'
  phase: string
  message_fa: string
  message_en: string
  error: string
  remotion: string | null
  updated_at: string
  project: boolean
  auto: boolean
  node_version_wanted: string
}

export interface RmKit {
  key: string
  theme_key: string
  name: string
  name_fa: string
  name_en: string
  animation: string
  animation_fa: string
  animation_en: string
  family: string
  realism: string
  fps_feel: number
  palette: { background: string; primary: string; secondary: string; accent: string; shadow: string; highlight: string }
  typography: { title_weight: 'regular' | 'bold' | 'black'; title_case: 'normal' | 'upper' | 'lower'; title_animation: 'none' | 'fade' | 'pop' | 'slide' | 'typewriter'; subtitle_color: string }
  mood: string
  builtin: boolean
}

export interface RmCode {
  compositions: { id: string; file: string; code: string }[]
  shared: { name: string; file: string; code: string }[]
}

export interface RmRenders {
  renders: {
    job_id: number
    status: string
    composition: string
    style: string
    size: string
    url: string
    kind: string
    seconds: number | null
    width: number | null
    height: number | null
    frames: number | null
    bytes: number | null
    created_at: string
    error: string
  }[]
}
