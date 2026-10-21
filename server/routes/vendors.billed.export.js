// Billed calls export, /api/vendors/billed/export: the calls
// billed in a range, one per row, to check against a vendor's invoice.

import { billed } from '#generated/Tld/Workbooks.js'
import { exportRoute } from '#tld/exportRoute.js'
import { billedFor, vendorName } from '#tld/vendorData.js'

export const GET = exportRoute(async (range, params) => {
  const vendor = (params.get('vendor_id') || '').trim()
  const [data, found] = await Promise.all([billedFor(range.start, range.end, vendor), vendorName(vendor)])
  return billed(range.start, range.end, found || 'all vendors', data.summary, data.rows)
})
