import { api } from '../../api/client'
import type { Preflight } from '../../api/types'
import type { Choice } from '../../components/feedback'

type Choose = (o: { title?: string; message: string; confirmLabel?: string; altLabel?: string }) => Promise<Choice>
type T = (key: string, params?: Record<string, string | number>) => string

/**
 * Pre-flight of «ساخت پیش‌نمایش / نسخهٔ نهایی»: a puppet shot whose character has no puppet would silently become a still picture with
 * a camera move. Ask first, and offer the one-click way out (an automatic stick-figure puppet) instead of falling back.
 * Returns whether to go on and whether the server should make the puppets first (`auto_rig`).
 */
export async function askAboutPuppets(episodeId: number, choose: Choose, t: T): Promise<{ go: boolean; auto_rig: boolean }> {
  let pf: Preflight
  try {
    pf = await api.get<Preflight>(`/episodes/${episodeId}/preflight`)
  } catch {
    return { go: true, auto_rig: false }              // the pre-flight is advice: never block production because it could not be read
  }
  if (!pf.needs_rig.length) return { go: true, auto_rig: false }
  const names = pf.needs_rig.map((r) => r.name || t('pf.host')).join('، ')
  const shots = pf.needs_rig.reduce((a, r) => a + r.shots, 0)
  const c = await choose({ title: t('pf.title'), message: t('pf.text', { names, n: shots }), confirmLabel: t('pf.auto'), altLabel: t('pf.skip') })
  if (c === 'no') return { go: false, auto_rig: false }
  return { go: true, auto_rig: c === 'yes' }
}
