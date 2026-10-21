// Shared by the TLD dashboard's routes in server/routes. Reads a
// request's date range and fetches the policies for it, once, however many
// routes ask at the same moment.
import { resolveRange } from '#generated/Tld/Dates.js'
import { policies } from '#generated/Tld/Queries.js'
import { send, todayEastern } from '#tld/egress.js'

const POLICIES_TIMEOUT_MS = 60000       // a quarter of policies is a large pull
const SHARED_FOR_MS = 20000             // the page loads the dashboard and the sales board together

// { start, end, label, error } from ?range=today… or ?range=custom&start=&end=
export function rangeFrom(request) {
  const params = new URL(request.url).searchParams
  return resolveRange({
    range: params.get('range') || 'today',
    start: params.get('start') || '',
    end: params.get('end') || '',
    today: todayEastern(),
  })
}

/*
 The page asks for /api/dashboard and /api/sales_board at the same time for
 the same range. One pull serves both, and a burst of auto refreshes inside
 the window reuses it. In memory, per instance, and gone in 20 seconds, so it
 never shows anything older than the page's own 30 second refresh would.
*/
const recent = new Map()                // `${start}|${end}` -> { at, promise }

export function policiesFor(start, end) {
  const key = `${start}|${end}`
  const hit = recent.get(key)
  if (hit && Date.now() - hit.at < SHARED_FOR_MS) return hit.promise

  const promise = send(policies(start, end), { timeoutMs: POLICIES_TIMEOUT_MS })
  recent.set(key, { at: Date.now(), promise })
  promise.catch(() => recent.delete(key))        // a failure is never shared
  return promise
}

export function noStore(body, init = {}) {
  return Response.json(body, { ...init, headers: { 'Cache-Control': 'no-store, private' } })
}

// A core/Tld/Workbooks.fs workbook sent as a download
export async function exportFile(book) {
  const { writeWorkbook, xlsxResponse } = await import('#tld/workbook.js')
  return xlsxResponse(await writeWorkbook(book), book.filename)
}

// The same failure shape the Python's exports used
export function exportFailed(error) {
  return noStore({ error: `Export failed: ${error.message}` }, { status: 500 })
}
