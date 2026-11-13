// The idea bank (instai/ideabank): ideas with a logline and a hook in both languages, search/filter facets, and the "start a project" answer.
export interface BankIdea {
  key: string
  builtin: boolean
  origin: string
  based_on: string
  category: string
  format: string
  tags: string[]
  title_fa: string
  title_en: string
  logline_fa: string
  logline_en: string
  hook_fa: string
  hook_en: string
  premise_fa: string
  premise_en: string
  suggested_styles: string[]
  episodes: number
  favorite: boolean
  hidden: boolean
  uses: number
}
export interface IdeaFacet {
  key: string
  fa: string
  en: string
  count: number
}
export interface IdeasPayload {
  ideas: BankIdea[]
  categories: IdeaFacet[]
  formats: IdeaFacet[]
  tags: { tag: string; count: number }[]
  total: number
  shown: number
}
export interface StartResult {
  page_id: number
  series_id: number
  series_url: string
  page_created: boolean
  look: Record<string, string>
}
export interface PreviewStatus {
  total: number
  done: number
  pending: number
  pending_keys: string[]
  workflow: string
  expected_seconds: number
}
