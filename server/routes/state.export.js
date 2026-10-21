// Production by State export, /api/state/export: deals by state
// and carrier, and with ?agents=1 by agent on a second sheet. Same pull and
// rules as the Dashboard tab.

import { byState } from '#generated/Tld/Workbooks.js'
import { dashboard } from '#generated/Tld/Policies.js'
import { exportRoute } from '#tld/exportRoute.js'
import { policiesFor } from '#tld/dashboardData.js'

export const GET = exportRoute(async (range, params) => {
  const data = dashboard(range, await policiesFor(range.start, range.end), 0, [])
  return byState(range.start, range.end, range.label, data.by_state, params.get('agents') === '1')
})
