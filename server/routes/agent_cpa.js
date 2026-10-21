// The TLD dashboard's cost figures, /api/agent_cpa: COST and CPA
// per agent, Total Spend, Blended CPA, Billable Calls and Conversion Rate. The
// page loads the Dashboard tab first and fills these in after, because TLD's
// cost report is the slowest call it makes. Read in core/Tld/Cpa.fs.

import { costReport } from '#generated/Tld/Queries.js'
import { report, hasData, failed } from '#generated/Tld/Cpa.js'
import { sendRaw } from '#tld/egress.js'
import { rangeFrom, noStore } from '#tld/dashboardData.js'

const REPORT_TIMEOUT_MS = 180000        // a month is ~30 s on TLD's side, a year far longer
const KEEP_FOR_MS = 5 * 60 * 1000       // cost barely moves minute to minute

/*
 Held per range for 5 minutes, in memory only, so the 30 second auto refresh
 and several people on the same range share one report instead of each
 starting a ~30 second one. A fetch already running is shared too. Refresh
 (?force=1) skips the held copy. An empty result is never held, so a bad
 answer is retried on the next request instead of showing zeros for minutes.
*/
const held = new Map()                  // `${start}|${end}` -> { at, result }
const running = new Map()               // `${start}|${end}` -> promise

function costFor(start, end, force) {
  const key = `${start}|${end}`
  const hit = held.get(key)
  if (!force && hit && Date.now() - hit.at < KEEP_FOR_MS) return Promise.resolve(hit.result)
  if (running.has(key)) return running.get(key)

  const promise = sendRaw(costReport(start, end), { timeoutMs: REPORT_TIMEOUT_MS })
    .then((payload) => {
      const result = report(payload)
      if (hasData(result)) held.set(key, { at: Date.now(), result })
      return result
    })
    .finally(() => running.delete(key))
  running.set(key, promise)
  return promise
}

export async function GET(request) {
  const range = rangeFrom(request)
  if (range.error) return noStore(failed(range.error), { status: 400 })

  try {
    const force = Boolean(new URL(request.url).searchParams.get('force'))
    return noStore(await costFor(range.start, range.end, force))
  } catch (error) {
    return noStore(failed(error.message))
  }
}
