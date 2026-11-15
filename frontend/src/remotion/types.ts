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
  motif?: string
  realism: string
  fps_feel: number
  palette: { background: string; primary: string; secondary: string; accent: string; shadow: string; highlight: string }
  typography: { title_weight: 'regular' | 'bold' | 'black'; title_case: 'normal' | 'upper' | 'lower'; title_animation: 'none' | 'fade' | 'pop' | 'slide' | 'typewriter'; subtitle_color: string }
  mood: string
  group?: string
  builtin: boolean
}

export interface RmCode {
  compositions: { id: string; file: string; code: string; same_as?: string }[]
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
    render_seconds?: number | null
    duration_sec?: number | null
    fps?: number | null
    width: number | null
    height: number | null
    frames: number | null
    bytes: number | null
    created_at: string
    error: string
  }[]
}

/** one finding of the rule checks (instai/motion_plan/qa.py) */
export interface MotionFinding {
  code: string
  label: string
  label_en: string
  severity: 'error' | 'warn' | 'info'
  scene: number | null
  message: string
  message_en: string
  auto: boolean
  shot?: { kind: string; frame: number }
}

export interface MotionValidate {
  spec: Record<string, any>
  notes: { fa: string; en: string }[]
  timeline: { starts: number[]; ends: number[]; total: number; fps: number }
  findings: MotionFinding[]
  summary_fa: string
  summary_en: string
}

export interface MotionNarrationPlan {
  spec: Record<string, any>
  origin: string
}

export interface MotionRound {
  n: number
  verdict: 'ok' | 'fix'
  issues: { scene: number; problem: string; severity: string }[]
  applied: Record<string, any>[]
  rejected: { op: Record<string, any>; why: string; why_en: string }[]
  before: { scene: number; frame: number; image_rel: string }[]
  after: { scene: number; frame: number; image_rel: string }[]
}

export interface MotionPlanDto {
  id: number
  shot_id: number | null
  title: string
  origin: string
  spec: Record<string, any> & { scenes: Record<string, any>[]; total_s?: number }
  rev: number
  can_undo: boolean
  can_redo: boolean
  qa: { fixed?: number; ok?: boolean; geometry?: boolean; geometry_error?: string; remaining?: MotionFinding[]; info?: MotionFinding[]; rounds?: { n: number; applied: { message: string; message_en: string }[] }[] }
  critique: { state?: string; message?: string; message_en?: string; rounds?: MotionRound[] }
  history?: { n: number; label: string; source: string; current: boolean; created_at: string }[]
}

export interface MotionShotState {
  shot_id: number
  technique: string
  plan: MotionPlanDto | null
  kit: RmKit
  size: 'landscape' | 'vertical' | 'square'
  seconds: number
  narration_ready: boolean
  lang: string
  edited: boolean
  stale: boolean
  clip: { asset_id: number; url: string; duration: number | null; current: boolean } | null
}
