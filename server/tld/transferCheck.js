// Runs the Transfer Check: reads the uploaded file (CSV through core/Tld/Csv.fs,
// Excel through core/Tld/Excel.fs) and fetches, step by step, what
// core/Tld/TransferCheck.fs asks for. Every decision is made there; this only
// sends requests and hands the answers back in order.
//
// The file's text is read in memory and never written anywhere. It carries MBI,
// DOB and Medicaid numbers; only phone, rep, campaign, time and TLD lead id are
// read from it.
import { read } from '#generated/Tld/Csv.js'
import {
  readFile, readDate, listRange, timeList, prepare, phonesOf, batches, callWindow,
  leadsMap, addLinkedBack, callsMap, leadIdsOf, policiesMap, score, droppedSales,
  BATCH, POLICY_BATCH,
} from '#generated/Tld/TransferCheck.js'
import {
  leadsForPhones, policiesCreatedLinks, inboundCalls, inboundCallTimes, policiesForLeads,
} from '#generated/Tld/Queries.js'
import { send } from '#tld/egress.js'

const AT_ONCE = 4                       // batches in flight together, answers kept in batch order

// A message for the person who uploaded the file, shown as is (a 400, not a failure)
export class CheckError extends Error {}

// Every batch's rows, in batch order, whatever order they come back in
async function inOrder(groups, request, timeoutMs) {
  const results = new Array(groups.length)
  let next = 0
  await Promise.all(
    Array.from({ length: Math.min(AT_ONCE, groups.length) }, async () => {
      while (next < groups.length) {
        const i = next++
        results[i] = await send(request(groups[i]), { timeoutMs })
      }
    })
  )
  return results
}

const flat = (groups) => groups.flat()

async function leadsFor(transfers) {
  return leadsMap(flat(await inOrder(batches(BATCH, phonesOf(transfers)), leadsForPhones, 180000)))
}

async function policiesFor(leads, transfers) {
  return policiesMap(await inOrder(batches(POLICY_BATCH, leadIdsOf(leads, transfers)), policiesForLeads, 180000))
}

/*
 The uploaded file as { header, records }. .xlsx and .xlsm are read as Excel,
 as the Python did; anything else as UTF-8 text, byte order mark dropped and
 bad bytes replaced.
*/
export async function readUpload(file) {
  const bytes = Buffer.from(await file.arrayBuffer())
  if (/\.xls[xm]$/i.test(file.name || '')) {
    const { readFirstSheet } = await import('#tld/workbook.js')
    try {
      return await readFirstSheet(bytes)
    } catch {
      throw new CheckError('That Excel file could not be read. Save it again from Excel, or as CSV.')
    }
  }
  return read(new TextDecoder('utf-8').decode(bytes))
}

export async function runTransferCheck({ table, phoneList, start, end }) {
  const { header, records } = table
  const parsed = readFile(header, records, phoneList)
  if (parsed.error) throw new CheckError(parsed.error)

  const from = readDate('start', start)
  const to = readDate('end', end)
  if (from.error || to.error) throw new CheckError(from.error || to.error)

  let transfers = parsed.transfers
  if (phoneList) {
    // the fronters' own list has no dates: each number is timed from its calls in the chosen week
    const problem = listRange(from.value, to.value)
    if (problem) throw new CheckError(problem)
    const callRows = flat(
      await inOrder(batches(BATCH, phonesOf(transfers)), (b) => inboundCallTimes(b, from.value, to.value), 300000)
    )
    transfers = timeList(transfers, callRows)
  }

  const step = prepare(transfers, from.value, to.value)
  if (step.error) throw new CheckError(step.error)
  const prepared = step.prepared

  // 1. leads on each phone, then linked leads pointing back
  const leads = await leadsFor(prepared.transfers)
  addLinkedBack(leads, await send(policiesCreatedLinks(prepared.d0, prepared.d1), { timeoutMs: 240000 }))

  // 2. inbound calls, a day of slack each side
  const [c0, c1] = callWindow(prepared.d0, prepared.d1)
  const calls = callsMap(
    flat(await inOrder(batches(BATCH, phonesOf(prepared.transfers)), (b) => inboundCalls(b, c0, c1), 300000))
  )

  // 3. every policy on those leads
  const policies = await policiesFor(leads, prepared.transfers)

  // the pay week guard: transfers outside the week that already sold
  let guard = null
  if (prepared.droppedRows.length) {
    const droppedLeads = await leadsFor(prepared.droppedRows)
    guard = droppedSales(prepared.droppedRows, droppedLeads, await policiesFor(droppedLeads, prepared.droppedRows), prepared.d0)
  }

  return score(prepared, leads, calls, policies, guard)
}
