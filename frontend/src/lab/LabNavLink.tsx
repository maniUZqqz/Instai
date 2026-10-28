import { Icon } from '../components/Icon'
import { NavLink } from '../components/ui'
import { useL } from './useL'

/** The one "Production lab" entry of the sidebar (Shell.tsx renders it after the main items). */
export function LabNavLink() {
  const { s } = useL()
  return (
    <NavLink to="/lab" className={({ isActive }) => (isActive ? 'active' : '')}>
      <Icon name="film" />
      {s('lab.nav')}
    </NavLink>
  )
}
