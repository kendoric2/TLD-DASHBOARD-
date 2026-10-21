// Tests for the shared TLD core, core/Tld. Run with `npm test`, which compiles
// the F# first; like touch.test.mjs these import the compiled output, because
// that is what the routes load.
//
// Expected values are the TLD dashboard's Python answers for the same input,
// written out, since that Python is on its way out.

import { test } from 'node:test'
import assert from 'node:assert/strict'

import { pyRound } from '../generated/Tld/Rows.js'
import { resolveRange } from '../generated/Tld/Dates.js'
import { rows, read } from '../generated/Tld/Csv.js'
import { parseTime, formatTime, readFile } from '../generated/Tld/TransferCheck.js'
import { dashboard, dedupeRows } from '../generated/Tld/Policies.js'

/*=======================================================
        ROUNDING
========================================================*/

// Python rounds an exact half to the even digit; toFixed rounds it up
test('pyRound matches Python round() on ties and near ties', () => {
  const cases = [
    [33.25, 1, 33.2], [33.35, 1, 33.4], [0.125, 2, 0.12], [0.375, 2, 0.38],
    [2.675, 2, 2.67], [-2.5, 0, -2], [3.5, 0, 4], [1.005, 2, 1], [49.999, 1, 50],
  ]
  for (const [x, places, python] of cases) assert.equal(pyRound(places, x), python, `round(${x}, ${places})`)
})

/*=======================================================
        DATE RANGES
========================================================*/

test('this week starts on Monday', () => {
  // 2026-10-20 is a Tuesday
  const r = resolveRange({ range: 'this_week', start: '', end: '', today: '2026-10-20' })
  assert.deepEqual([r.start, r.end, r.label, r.error], ['2026-10-19', '2026-10-20', 'This Week', null])
})

test('last month and this quarter', () => {
  const lm = resolveRange({ range: 'last_month', start: '', end: '', today: '2026-03-10' })
  assert.deepEqual([lm.start, lm.end], ['2026-02-01', '2026-02-28'])
  const q = resolveRange({ range: 'this_quarter', start: '', end: '', today: '2026-11-05' })
  assert.deepEqual([q.start, q.end], ['2026-10-01', '2026-11-05'])
})

test('custom ranges are checked and labelled', () => {
  const ok = resolveRange({ range: 'custom', start: '2026-06-01', end: '2026-06-15', today: '2026-10-20' })
  assert.equal(ok.label, 'Jun 1 – Jun 15, 2026')
  const backwards = resolveRange({ range: 'custom', start: '2026-10-09', end: '2026-10-01', today: '2026-10-20' })
  assert.equal(backwards.error, "End date can't be before the start date.")
  const tooLong = resolveRange({ range: 'custom', start: '2025-01-01', end: '2026-06-01', today: '2026-10-20' })
  assert.equal(tooLong.error, "Custom range can't exceed 12 months.")
})

/*=======================================================
        CSV, AS PYTHON'S csv MODULE READS IT
========================================================*/

test('quoted commas, doubled quotes and line breaks inside quotes', () => {
  assert.deepEqual(rows('a,b,c\r\n1,"x, y",3\n\n4,"say ""hi""",\n"multi\nline",5\r'), [
    ['a', 'b', 'c'], ['1', 'x, y', '3'], ['4', 'say "hi"', ''], ['multi\nline', '5'],
  ])
})

test('a lone "" is a row, a blank line is not, and a mid field quote is a character', () => {
  assert.deepEqual(rows('x\n""\n,\n a, "b"c\n'), [['x'], [''], ['', ''], [' a', ' "b"c']])
})

test('records: short rows leave null, long rows are trimmed, the byte order mark goes', () => {
  assert.deepEqual(read('﻿h1,h2\nv1\nv1,v2,extra').records, [{ h1: 'v1', h2: null }, { h1: 'v1', h2: 'v2' }])
})

/*=======================================================
        TRANSFER CHECK
========================================================*/

test('times parse in the formats DialedIN and TLD use, and nothing else', () => {
  const at = (s) => { const v = parseTime(s); return v == null ? null : formatTime(v) }
  assert.equal(at('10/17/2026 4:31:25 PM'), '2026-10-17 16:31:25')
  assert.equal(at('10/17/2026 12:05 AM'), '2026-10-17 00:05:00')
  assert.equal(at('2026-10-17 16:31:21'), '2026-10-17 16:31:21')
  assert.equal(at('10/17/2026'), '2026-10-17 00:00:00')
  assert.equal(at('2026-02-30'), null)
  assert.equal(at('10/17/2026 13:05 PM'), null)
})

// No timezone, so a daylight saving night does not move anything
test('a daylight saving night is ordinary wall clock time', () => {
  assert.equal(formatTime(parseTime('3/8/2026 2:30:00 AM')), '2026-03-08 02:30:00')
  assert.equal(parseTime('11/1/2026 1:30:00 AM') < parseTime('11/1/2026 1:45:00 AM'), true)
})

test('CallDetails: only the fronter leg, and never DialedIN\'s own Lead ID', () => {
  const { header, records } = read(
    'Date,Rep,Campaign,Phone,Lead ID,Details\n' +
    '10/09/2026 5:00:24 PM,5613630948,Manhattan Life,(555) 010-0001,123456789,Blind Transfer\n' +
    '10/09/2026 5:00:24 PM,jeanr@ihp,Manhattan Life,(555) 010-0001,123456789,Transferred Call\n'
  )
  const out = readFile(header, records, false)
  assert.equal(out.error, null)
  assert.equal(out.transfers.length, 1)
  assert.equal(out.transfers[0].rep, 'jeanr@ihp')
  assert.equal(out.transfers[0].phone, '5550100001')
  assert.equal(out.transfers[0].tldId, '')
})

test('BlindTransfer: the customer comes from Caller ID when Phone is the transfer lines', () => {
  const lines = ['Date,Rep,Campaign,Phone,Caller ID,Details']
  for (let n = 0; n < 25; n++) {
    lines.push(`10/16/2026 2:${String(n).padStart(2, '0')}:00 PM,rep@ihp,_MANUAL_CALL_,${n % 5 ? '5613630948' : '5617851493'},1555010${String(n).padStart(4, '0')},`)
  }
  const { header, records } = read(lines.join('\n'))
  const out = readFile(header, records, false)
  assert.equal(out.transfers[7].phone, '5550100007')
})

/*=======================================================
        EXCEL
========================================================*/

test('numbers in export headers read as Python formatted them', async () => {
  const { commas, money, safeName, sheetTitle } = await import('../generated/Tld/Workbooks.js')
  assert.equal(commas(1234567), '1,234,567')
  assert.equal(commas(999), '999')
  assert.equal(money(17520), '$17,520.00')
  assert.equal(money(1234.5), '$1,234.50')
  assert.equal(safeName('Powers, Tony'), 'Powers-Tony')
  assert.equal(safeName('all vendors'), 'all-vendors')
  assert.equal(sheetTitle('a/b:c'), 'a b c')
  assert.equal(sheetTitle('x'.repeat(40)).length, 31)
})

test('a workbook round trips through exceljs: empty rows kept, cells as written', async () => {
  const { write, read } = await import('../generated/Tld/Excel.js')
  const book = {
    filename: 'x.xlsx',
    sheets: [{ name: 'One', rows: [['A', 'B'], [], [1, null], ['5550100001', 2.5]], textColumn: 1, fromRow: 4, widths: [12] }],
  }
  const table = await read(Buffer.from(await write(book)))
  assert.deepEqual(table.header, ['A', 'B'])
  assert.equal(table.records.length, 3)
  assert.deepEqual(table.records[1], { A: 1, B: '' })
  assert.deepEqual(table.records[2], { A: '5550100001', B: 2.5 })
})

/*=======================================================
        POLICIES
========================================================*/

test('a sale counts once, redacted never, and GTL is out of Policies Sold but in the chart', () => {
  const rows = [
    { policy_id: 1, lead_id: 9, stage: 'sale', carrier_name: 'UHC', fronter_id: '5', agent_name: 'Al' },
    { policy_id: 1, lead_id: 9, stage: 'sale', carrier_name: 'UHC' },
    { policy_id: 2, stage: 'Redacted', carrier_name: 'UHC' },
    { policy_id: 3, stage: 'sale', carrier_name: 'GTL', agent_name: 'Al' },
  ]
  assert.equal(dedupeRows(rows).length, 2)
  const d = dashboard({ start: '2026-10-20', end: '2026-10-20', label: 'Today' }, rows, 0, [])
  assert.equal(d.kpis.policies_sold, 1)
  assert.deepEqual(d.by_carrier.map((c) => [c.label, c.count]), [['UHC', 1], ['GTL', 1]])
})
