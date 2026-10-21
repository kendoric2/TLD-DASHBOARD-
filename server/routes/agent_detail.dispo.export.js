// One person's call dispositions export, /api/agent_detail/dispo/export.

import { dispositions, safeName, commas } from '#generated/Tld/Workbooks.js'
import { exportRoute, ExportProblem } from '#tld/exportRoute.js'
import { agentDispoFor } from '#tld/agentData.js'

export const GET = exportRoute(async (range, params) => {
  const agent = (params.get('agent') || '').trim()
  if (!agent) throw new ExportProblem('Choose a person before exporting.')
  const d = await agentDispoFor(range.start, range.end, agent)
  const notes = [
    `Range: ${range.start} to ${range.end}`,
    `Total calls: ${commas(d.total)}`,
    'Automated dialling is logged separately, so these are calls this person handled.',
  ]
  return dispositions(`Call dispositions — ${agent}`, notes, d.dispositions, d.total, agent,
    `CallDispositions_${safeName(agent)}_${range.start}_${range.end}.xlsx`)
})
