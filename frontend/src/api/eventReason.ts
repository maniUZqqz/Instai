import type { Params } from '../i18n'

/** The reasons the program writes into an episode's history are English words stored as they were (old rows stay as they are); the Persian interface shows them in Persian. */
const SLUG: Record<string, string> = {
  'series plan': 'series_plan',
  'generate script': 'gen_script',
  'script ready': 'script_ready',
  'script generation did not finish': 'script_unfinished',
  'no script job is running: back to planned': 'script_no_job',
  'script approved': 'script_approved',
  'script approved for storyboard': 'script_approved_sb',
  'script written by hand': 'script_hand',
  'rework: new script': 'rework_script',
  'rework: new storyboard': 'rework_sb',
  'rework: storyboard edited': 'rework_sb_edit',
  'storyboard approved': 'sb_approved',
  retry: 'retry',
  'video shots': 'video_shots',
  'assets ready': 'assets_ready',
  'clips done': 'clips_done',
  'render finished': 'render_done',
  'quality review accepted by owner': 'qc_accepted',
  'approved by owner': 'approved',
  'approval revoked': 'approval_revoked',
  scheduled: 'scheduled',
  'marked as published by the owner': 'published_hand',
  'published through the official API (explicitly enabled)': 'published_api',
  'automatic: next episode': 'auto_next',
  'automatic: script approved': 'auto_script_ok',
  'automatic: publication slot': 'auto_slot',
  'added by hand': 'added_by_hand',
  manual: 'manual',
}

type T = (key: string, params?: Params) => string

export function eventReason(reason: string, lang: string, t: T): string {
  if (!reason || lang !== 'fa') return reason
  const slug = SLUG[reason]
  if (slug) return t('evr.' + slug)
  let m = /^produce \((preview|final)\)$/.exec(reason)
  if (m) return t('evr.produce_' + m[1])
  m = /^quality checks passed \((\d+) warnings?\)$/.exec(reason)
  if (m) return t('evr.qc_passed', { n: Number(m[1]) })
  if (reason.startsWith('published through the official API on the owner')) return t('evr.published_api_owner')
  return reason
}
