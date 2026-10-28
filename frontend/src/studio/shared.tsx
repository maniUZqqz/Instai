import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { Button, Empty, LinkButton, Loading, Notice, SelectField, TextField } from '../components/ui'
import { useToast } from '../components/feedback'
import { useAction, useQuery } from '../hooks'
import type { CharacterLite, PageLite } from './api'
import { useS } from './useS'

/** Re-render every `ms` while mounted (countdowns). */
export function useTicker(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(id)
  }, [ms])
  return now
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onerror = () => reject(r.error)
    r.onload = () => {
      const res = String(r.result || '')
      resolve(res.includes(',') ? res.slice(res.indexOf(',') + 1) : res)
    }
    r.readAsDataURL(file)
  })
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const { s } = useS()
  const toast = useToast()
  const [done, setDone] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
      } catch {
        /* the text stays visible on screen anyway */
      }
      ta.remove()
    }
    setDone(true)
    toast.ok(s('common.copied'))
    window.setTimeout(() => setDone(false), 1500)
  }
  return (
    <Button size="sm" icon={done ? 'check' : 'copy'} onClick={copy} aria-label={label ?? s('common.copy')}>
      {label ?? s('common.copy')}
    </Button>
  )
}

export function licenceTone(commercial: string): 'ok' | 'warn' | 'err' | 'neutral' {
  return commercial === 'yes' ? 'ok' : commercial === 'no' ? 'err' : commercial === 'unknown' ? 'warn' : 'neutral'
}

export interface Picked {
  page: PageLite | null
  character: CharacterLite | null
  pageId: number | null
  characterId: number | null
}

/**
 * Page -> character pickers kept in the URL (?page=&character=). Shows the empty states itself and renders `children(picked)` only
 * when a character is chosen. A character can be added inline (a name) so nobody is stuck on an empty page.
 */
export function PageCharacterPicker({ children }: { children: (p: Picked & { reloadCharacters: () => void }) => ReactNode }) {
  const { s } = useS()
  const [params, setParams] = useSearchParams()
  const pages = useQuery<PageLite[]>('/pages')
  const pageParam = Number(params.get('page')) || null
  const pageId = pageParam && pages.data?.some((p) => p.id === pageParam) ? pageParam : (pages.data?.[0]?.id ?? null)
  const chars = useQuery<CharacterLite[]>(pageId ? `/pages/${pageId}/characters` : null)
  const charParam = Number(params.get('character')) || null
  const characterId = charParam && chars.data?.some((c) => c.id === charParam) ? charParam : (chars.data?.[0]?.id ?? null)
  const act = useAction()
  const [newName, setNewName] = useState('')

  const set = useCallback(
    (next: { page?: number | null; character?: number | null }) => {
      const p = new URLSearchParams(params)
      if (next.page !== undefined) {
        if (next.page) p.set('page', String(next.page))
        else p.delete('page')
        p.delete('character')
      }
      if (next.character !== undefined) {
        if (next.character) p.set('character', String(next.character))
        else p.delete('character')
      }
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  if (pages.loading) return <Loading />
  if (!pages.data || pages.data.length === 0) {
    return <Empty icon="pages" title={s('pick.no_pages')} text={s('pick.no_pages_text')} action={<LinkButton to="/pages/new" variant="primary" icon="plus">{s('pick.new_page')}</LinkButton>} />
  }
  const page = pages.data.find((p) => p.id === pageId) ?? null
  const character = chars.data?.find((c) => c.id === characterId) ?? null
  const addCharacter = () =>
    act.run(
      async () => {
        const c = await api.post<CharacterLite>(`/pages/${pageId}/characters`, { name: newName.trim(), role: '' })
        setNewName('')
        chars.reload()
        set({ character: c.id })
      },
      { success: s('pick.added') },
    )

  return (
    <div className="stack-lg">
      <div className="card flat">
        <div className="grid-2">
          <SelectField
            label={s('pick.page')}
            value={String(pageId ?? '')}
            onChange={(v) => set({ page: Number(v) })}
            options={pages.data.map((p) => ({ value: String(p.id), label: p.name }))}
          />
          <SelectField
            label={s('pick.character')}
            value={String(characterId ?? '')}
            onChange={(v) => set({ character: Number(v) })}
            disabled={!chars.data || chars.data.length === 0}
            options={(chars.data ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
          />
        </div>
        {chars.data && chars.data.length === 0 && (
          <div className="stack-sm" style={{ marginBlockStart: '0.75rem' }}>
            <Notice tone="info">{s('pick.no_characters')}</Notice>
            <div className="row nw">
              <div className="grow">
                <TextField label={s('pick.new_character')} value={newName} onChange={setNewName} maxLength={120} />
              </div>
              <Button variant="primary" icon="plus" busy={act.busy} disabled={!newName.trim()} onClick={addCharacter}>
                {s('pick.add_character')}
              </Button>
            </div>
          </div>
        )}
      </div>
      {chars.loading && <Loading />}
      {character && page && children({ page, character, pageId: page.id, characterId: character.id, reloadCharacters: chars.reload })}
    </div>
  )
}
