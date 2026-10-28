import { Route } from 'react-router-dom'
import Hub from './Hub'
import { LAB_SCREENS } from './registry'

/** Routes of the Production lab screens, placed inside the app shell's <Route> in App.tsx:  {labRoutes} */
export const labRoutes = (
  <Route path="lab">
    <Route index element={<Hub />} />
    {LAB_SCREENS.filter((sc) => sc.Component).map((sc) => {
      const C = sc.Component!
      return <Route key={sc.key} path={sc.path} element={<C />} />
    })}
  </Route>
)
