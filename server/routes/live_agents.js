// The TLD dashboard's Live Agents board, /api/live_agents. Who is
// on the dialer right now, with role and, mid call, the lead. Decided in
// core/Tld/LiveAgents.fs.

import { liveAgents, crmUsers, leadsByPhone } from '#generated/Tld/Queries.js'
import { board, incallPhones, leadsPerPhone } from '#generated/Tld/LiveAgents.js'
import { send, nowEastern } from '#tld/egress.js'
import { noStore } from '#tld/dashboardData.js'

export async function GET() {
  // Roles are a nice to have: a CRM hiccup shows "unknown" rather than an empty board
  const [live, users] = await Promise.allSettled([
    send(liveAgents(), { timeoutMs: 60000 }),
    send(crmUsers(), { timeoutMs: 60000 }),
  ])
  if (live.status === 'rejected') {
    return noStore({ error: `Could not load live agents: ${live.reason.message}` }, { status: 500 })
  }

  const phones = incallPhones(live.value)
  let leads = null
  if (phones.length) {
    leads = await send(leadsByPhone(phones, leadsPerPhone), { timeoutMs: 30000 }).catch(() => null)
  }

  return noStore(board(live.value, users.status === 'fulfilled' ? users.value : null, leads, nowEastern()))
}
