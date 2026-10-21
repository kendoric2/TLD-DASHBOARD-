// The TLD dashboard's sales board, /api/sales_board. Agents and
// fronters together, optionally one carrier. Decided in core/Tld/Policies.fs.

import { board } from '#generated/Tld/Policies.js'
import { rangeFrom, policiesFor, noStore } from '#tld/dashboardData.js'

export async function GET(request) {
  const range = rangeFrom(request)
  if (range.error) return noStore({ error: range.error }, { status: 400 })

  try {
    const rows = await policiesFor(range.start, range.end)
    const carrier = new URL(request.url).searchParams.get('carrier') || ''
    return noStore(board(range, rows, carrier))
  } catch (error) {
    return noStore({ error: `Could not load the sales board: ${error.message}`, demo: false })
  }
}
