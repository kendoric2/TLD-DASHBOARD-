// The TLD dashboard's Vendors tab, /api/vendors: the vendor list
// and lead intake always, and cost, billed calls and the disposition breakdown
// when the page asks (?cost=1, ?billed=1, ?dispo=1). The pulls are in
// lib/tld/vendorData.js, shared with the exports; every number is decided in
// core/Tld/Vendors.fs.

import { rangeFrom, noStore } from '#tld/dashboardData.js'
import { vendorCatalogue, leadsFor, costFor, billedFor, dispositionsFor } from '#tld/vendorData.js'

export async function GET(request) {
  const range = rangeFrom(request)
  if (range.error) return noStore({ error: range.error }, { status: 400 })

  const params = new URL(request.url).searchParams
  const vendor = (params.get('vendor_id') || '').trim()
  // Billing is inbound only; outbound is the auto dialer working lists and says nothing about a vendor
  let direction = (params.get('direction') || 'INBOUND').toUpperCase()
  if (direction === 'ALL') direction = ''

  const list = vendorCatalogue()
  const jobs = {
    vendors: list,
    leads: leadsFor(range.start, range.end, vendor, list),
    dispo: params.get('dispo') ? dispositionsFor(range.start, range.end, vendor, direction) : null,
    cost: params.get('cost') ? costFor(range.start, range.end, vendor) : null,
    billed: params.get('billed') ? billedFor(range.start, range.end, vendor) : null,
  }

  const data = {
    demo: false,
    range_label: range.label,
    vendor_id: vendor || null,
    date_range: { start: range.start, end: range.end },
  }
  const errors = []
  const names = Object.keys(jobs)
  const settled = await Promise.allSettled(names.map((name) => jobs[name]))
  settled.forEach((outcome, i) => {
    if (outcome.status === 'fulfilled') {
      data[names[i]] = outcome.value ?? null
    } else {
      data[names[i]] = null
      errors.push(`${names[i]}: ${outcome.reason?.message || outcome.reason}`)
    }
  })
  if (errors.length) data.errors = errors

  return noStore(data)
}
