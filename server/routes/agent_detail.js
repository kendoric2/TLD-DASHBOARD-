// The TLD dashboard's Agent Detail tab, /api/agent_detail. One
// person's deals closed and enrolled, with SEP, and with ?dispo=1 their call
// outcomes. Pulls in lib/tld/agentData.js; decided in core/Tld/AgentDetail.fs.

import { rangeFrom, noStore } from '#tld/dashboardData.js'
import { agentDetailFor, agentDispoFor } from '#tld/agentData.js'

export async function GET(request) {
  const range = rangeFrom(request)
  if (range.error) return noStore({ error: range.error }, { status: 400 })

  const params = new URL(request.url).searchParams
  const agent = params.get('agent') || ''

  try {
    if (params.get('dispo')) {
      const result = await agentDispoFor(range.start, range.end, agent)
      return noStore({ dispo: result, agent: agent || null, range_label: range.label, demo: false })
    }
    return noStore(await agentDetailFor(range.start, range.end, agent, range.label))
  } catch (error) {
    return noStore({ people: [], rows: [], error: error.message, summary: { closed: 0, enrolled: 0, total: 0 } })
  }
}
