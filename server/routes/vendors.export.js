// Vendors export, /api/vendors/export: the table as on screen and
// a Sold Policies sheet (date sold, phone) behind its Sold column.

import { vendors } from '#generated/Tld/Workbooks.js'
import { exportRoute } from '#tld/exportRoute.js'
import { vendorCatalogue, leadsFor, soldPoliciesFor } from '#tld/vendorData.js'

export const GET = exportRoute(async (range, params) => {
  const vendor = (params.get('vendor_id') || '').trim()
  const list = vendorCatalogue()
  const [intake, catalogue, sold] = await Promise.all([
    leadsFor(range.start, range.end, vendor, list),
    list,
    soldPoliciesFor(range.start, range.end, vendor),
  ])
  const byId = new Map(catalogue.map((v) => [String(v.vendor_id), v]))
  const name = (vendor && byId.get(vendor)?.name) || 'all vendors'
  const rows = intake.by_vendor.map((r) => {
    const c = byId.get(r.vendor_id) || {}
    return { ...r, price: c.price_inbound || c.price || null, status: c.status ?? '' }
  })
  return vendors(range.start, range.end, name, rows, intake.totals, sold)
})
