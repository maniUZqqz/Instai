import { Route } from 'react-router-dom'
import Hub from './Hub'
import { STUDIO_SCREENS } from './registry'

/** Routes of the Studio screens, placed inside the app shell's <Route> in App.tsx:  {studioRoutes} */
export const studioRoutes = (
  <Route path="studio">
    <Route index element={<Hub />} />
    {STUDIO_SCREENS.filter((sc) => sc.Component).map((sc) => {
      const C = sc.Component!
      return <Route key={sc.key} path={sc.path} element={<C />} />
    })}
  </Route>
)
