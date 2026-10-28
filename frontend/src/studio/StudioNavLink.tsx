import { Icon } from '../components/Icon'
import { NavLink } from '../components/ui'
import { useS } from './useS'

/** The one "Studio" entry of the sidebar (Shell.tsx renders it after the main items). */
export function StudioNavLink() {
  const { s } = useS()
  return (
    <NavLink to="/studio" className={({ isActive }) => (isActive ? 'active' : '')}>
      <Icon name="film" />
      {s('studio.nav')}
    </NavLink>
  )
}
