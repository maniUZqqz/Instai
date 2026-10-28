import { Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Empty, LinkButton } from './components/ui'
import { useI18n } from './i18n'
import Dashboard from './pages/Dashboard'
import PagesList from './pages/PagesList'
import SeriesBuilder from './pages/SeriesBuilder'
import Wizard from './pages/Wizard'
import { CharactersTab } from './pages/workspace/CharactersTab'
import PublishingCentre, { PublishingTab } from './pages/workspace/Publishing'
import { ProfilesTab } from './pages/workspace/ProfilesTab'
import { EpisodesTab, HistoryTab, Overview, SeriesTab, Workspace } from './pages/workspace/Workspace'

function NotFound() {
  const { t } = useI18n()
  return (
    <Empty
      icon="alert"
      title={t('notfound.title')}
      text={t('notfound.text')}
      action={
        <LinkButton to="/" variant="primary" icon="home">
          {t('nav.dashboard')}
        </LinkButton>
      }
    />
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="pages" element={<PagesList />} />
        <Route path="pages/new" element={<Wizard />} />
        <Route path="pages/:id" element={<Workspace />}>
          <Route index element={<Overview />} />
          <Route path="settings" element={<ProfilesTab />} />
          <Route path="characters" element={<CharactersTab />} />
          <Route path="series" element={<SeriesTab />} />
          <Route path="episodes" element={<EpisodesTab />} />
          <Route path="publishing" element={<PublishingTab />} />
          <Route path="history" element={<HistoryTab />} />
        </Route>
        <Route path="series/:id" element={<SeriesBuilder />} />
        <Route path="publishing" element={<PublishingCentre />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
