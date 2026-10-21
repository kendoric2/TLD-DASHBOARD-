// The TLD dashboard's Dashboard tab, /api/dashboard. Every number
// is decided in core/Tld/Policies.fs; this fetches the 2 pulls it needs and
// hands them over. Takes precedence over the Python pass through in
// ../[[...path]] for this one path.

import { dashboard } from '#generated/Tld/Policies.js'
import { averagePremium } from '#generated/Tld/Queries.js'
import { firstNum } from '#generated/Tld/Rows.js'
import { send } from '#tld/egress.js'
import { rangeFrom, policiesFor, noStore } from '#tld/dashboardData.js'

export async function GET(request) {
  const range = rangeFrom(request)
  if (range.error) return noStore({ error: range.error }, { status: 400 })

  // Both at once. One failing still shows the other, named, as the Python did.
  const [policyRows, premium] = await Promise.allSettled([
    policiesFor(range.start, range.end),
    send(averagePremium(range.start, range.end)),
  ])

  const errors = []
  if (policyRows.status === 'rejected') errors.push(`policy_rows: ${policyRows.reason.message}`)
  if (premium.status === 'rejected') errors.push(`avg_gtl: ${premium.reason.message}`)

  return noStore(
    dashboard(
      range,
      policyRows.status === 'fulfilled' ? policyRows.value : [],
      premium.status === 'fulfilled' ? firstNum(premium.value) : 0,
      errors
    )
  )
}
