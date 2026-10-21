// Active Policies export, /api/active/export: active vs sold per
// carrier, from the same pull and rules as the Dashboard tab.

import { active } from '#generated/Tld/Workbooks.js'
import { dashboard } from '#generated/Tld/Policies.js'
import { exportRoute } from '#tld/exportRoute.js'
import { policiesFor } from '#tld/dashboardData.js'

export const GET = exportRoute(async (range) => {
  const data = dashboard(range, await policiesFor(range.start, range.end), 0, [])
  return active(range.start, range.end, range.label, data.active_by_carrier)
})
