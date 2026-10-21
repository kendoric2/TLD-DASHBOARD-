// The TLD pulls behind the Vendors tab and its exports, so a file can never
// disagree with the screen. Every number is decided in core/Tld/Vendors.fs.
import {
  vendorList, leadsCreated, vendorCost, billedCalls, callsOnDay, callCount, leadsCreatedByState,
  leadsCreatedWithPhone, soldPoliciesForLeads,
} from '#generated/Tld/Queries.js'
import {
  catalogue, leads, cost, billed, dayCounts, dayTotal, disagrees, breakdown, stateReport, soldLeadIds, soldPolicies,
} from '#generated/Tld/Vendors.js'
import { firstNum } from '#generated/Tld/Rows.js'
import { send, sendRaw, todayEastern } from '#tld/egress.js'
import { policiesFor } from '#tld/dashboardData.js'

const BIG_PULL_MS = 240000              // a month of leads or calls
const COST_MS = 180000
const DAYS_AT_ONCE = 6                  // the Python's thread count
const MAX_DAYS = 400
const LEADS_PER_POLICY_PULL = 50        // the policies endpoint takes lead_id as a list

export function daysBetween(start, end) {
  const days = []
  for (let d = new Date(`${start}T00:00:00Z`); days.length < MAX_DAYS; d.setUTCDate(d.getUTCDate() + 1)) {
    const iso = d.toISOString().slice(0, 10)
    if (iso > end) break
    days.push(iso)
  }
  return days
}

// work over items, size at a time, results in item order
export async function inBatches(items, size, work) {
  const results = new Array(items.length)
  let next = 0
  await Promise.all(
    Array.from({ length: Math.min(size, items.length) }, async () => {
      while (next < items.length) {
        const i = next++
        results[i] = await work(items[i])
      }
    })
  )
  return results
}

export function vendorCatalogue() {
  return send(vendorList(), { timeoutMs: 60000 }).then(catalogue)
}

// Lead intake per vendor; names come from the catalogue, and a catalogue failure only costs the names
export async function leadsFor(start, end, vendor, catalogueList) {
  const [rows, list] = await Promise.all([
    send(leadsCreated(start, end, vendor), { timeoutMs: BIG_PULL_MS }),
    (catalogueList || vendorCatalogue()).catch(() => []),
  ])
  return leads(rows, list)
}

export function costFor(start, end, vendor) {
  return sendRaw(vendorCost(start, end, vendor), { timeoutMs: COST_MS }).then(cost)
}

/*
 Billed calls one day at a time. One request for a week of billed calls is too
 large a payload to come back before TLD's gateway answers 504 at about 60 s,
 so each request is bounded to a day, which returns. Days go in date order and
 Tld.Vendors.billed sorts the result, so the answer is the same as one request
 would give. Unlike dispositions, a failed day fails the whole pull: this is
 the audit trail behind an invoice, and a total missing a day must not show.
*/
export async function billedFor(start, end, vendor) {
  const perDay = inBatches(daysBetween(start, end), DAYS_AT_ONCE, async (day) => {
    try {
      return await send(billedCalls(day, day, vendor), { timeoutMs: BIG_PULL_MS })
    } catch (error) {
      throw new Error(`${day}: ${error.message}`)
    }
  })
  const [days, policyRows] = await Promise.all([perDay, policiesFor(start, end).catch(() => [])])
  return billed(days.flat(), policyRows)
}

/*
 Finished days of dispositions, in memory per instance. A day before today
 never changes, so it is pulled once; today is always pulled. Dropped
 wholesale when TLD's own count of the range disagrees with ours.
*/
const finishedDays = new Map()          // `${day}|${vendor}|${direction}` -> counts

export async function dispositionsFor(start, end, vendor, direction) {
  const today = todayEastern()
  const days = daysBetween(start, end)
  const keyOf = (day) => `${day}|${vendor}|${direction}`
  let cachedDays = 0

  const counts = await inBatches(days, DAYS_AT_ONCE, async (day) => {
    const kept = finishedDays.get(keyOf(day))
    if (kept) {
      cachedDays += 1
      return kept
    }
    try {
      const result = dayCounts(await send(callsOnDay(day, vendor, direction), { timeoutMs: BIG_PULL_MS }))
      if (day < today && dayTotal(result) > 0) finishedDays.set(keyOf(day), result)
      return result
    } catch {
      return null                       // a failed day is left out, as the Python did
    }
  })

  const ours = counts.reduce((sum, day) => sum + (day ? dayTotal(day) : 0), 0)
  let theirs = ours
  try {
    theirs = firstNum(await send(callCount(start, end, vendor, direction), { timeoutMs: 90000 }))
  } catch {
    // keep ours; the check is a cross check, not a requirement
  }
  if (disagrees(ours, theirs)) {
    days.forEach((day) => finishedDays.delete(keyOf(day)))
    console.warn('[tld vendors] %s..%s: counted %d but TLD says %d, kept days dropped', start, end, ours, theirs)
  }
  return breakdown(counts, theirs, cachedDays)
}

export async function stateReportFor(start, end) {
  const [rows, list] = await Promise.all([
    send(leadsCreatedByState(start, end), { timeoutMs: BIG_PULL_MS }),
    vendorCatalogue().catch(() => []),
  ])
  return stateReport(rows, list)
}

// The vendor export's Sold Policies sheet: the policies behind the Sold column
export async function soldPoliciesFor(start, end, vendor) {
  const leadRows = await send(leadsCreatedWithPhone(start, end, vendor), { timeoutMs: BIG_PULL_MS })
  const ids = soldLeadIds(leadRows)
  const batches = []
  for (let i = 0; i < ids.length; i += LEADS_PER_POLICY_PULL) batches.push(ids.slice(i, i + LEADS_PER_POLICY_PULL))
  const policyRows = (await inBatches(batches, 4, (batch) => send(soldPoliciesForLeads(batch), { timeoutMs: 180000 }))).flat()
  return soldPolicies(leadRows, policyRows)
}

// A vendor's name for a file, or "" for every vendor
export async function vendorName(vendor, catalogueList) {
  if (!vendor) return ''
  const list = await (catalogueList || vendorCatalogue())
  return list.find((v) => String(v.vendor_id) === String(vendor))?.name || ''
}
