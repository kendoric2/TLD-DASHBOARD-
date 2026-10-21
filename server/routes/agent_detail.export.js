// Agent Detail export, /api/agent_detail/export: one person's
// deals, in the order the page has them sorted.

import { agentDetail, sortRows } from '#generated/Tld/Workbooks.js'
import { exportRoute, ExportProblem } from '#tld/exportRoute.js'
import { agentDetailFor } from '#tld/agentData.js'

export const GET = exportRoute(async (range, params) => {
  const agent = (params.get('agent') || '').trim()
  if (!agent) throw new ExportProblem('Choose a person before exporting.')
  const data = await agentDetailFor(range.start, range.end, agent, range.label)
  const rows = sortRows(data.rows || [], params.get('sort') || 'date_sold', (params.get('dir') || '-1') === '-1')
  return agentDetail(agent, range.start, range.end, rows)
})
