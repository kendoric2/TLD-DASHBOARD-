// Call dispositions export for a vendor, /api/vendors/dispo/export.

import { dispositions, safeName, commas } from '#generated/Tld/Workbooks.js'
import { exportRoute } from '#tld/exportRoute.js'
import { dispositionsFor, vendorName } from '#tld/vendorData.js'

const DIRECTIONS = { INBOUND: 'Inbound only', OUTBOUND: 'Outbound only' }

export const GET = exportRoute(async (range, params) => {
  const vendor = (params.get('vendor_id') || '').trim()
  const direction = (params.get('direction') || 'INBOUND').toUpperCase()
  const [d, found] = await Promise.all([
    dispositionsFor(range.start, range.end, vendor, direction === 'ALL' ? '' : direction),
    vendorName(vendor),
  ])
  const name = found || 'All vendors'
  const notes = [
    `Range: ${range.start} to ${range.end}`,
    `Direction: ${DIRECTIONS[direction] || 'All calls'}`,
    `Total calls: ${commas(d.total)}`,
  ]
  if (d.filtered_spam) notes.push(`Excluded: ${commas(d.filtered_spam)} robocalls caught by TLD's DID filter`)
  return dispositions(`Call dispositions — ${name}`, notes, d.dispositions, d.total, name,
    `CallDispositions_${safeName(name)}_${range.start}_${range.end}.xlsx`)
})
