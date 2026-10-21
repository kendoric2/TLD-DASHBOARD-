// The Transfer Check for payroll, /api/transfer_check/export: the
// page posts back the signed result it was given, and gets the workbook. A
// result whose signature no longer matches is refused, so the file is always
// what the check produced.

import { transfers } from '#generated/Tld/Workbooks.js'
import { unseal } from '#tld/sealed.js'
import { noStore, exportFile, exportFailed } from '#tld/dashboardData.js'

const EXPIRED = 'That check has expired — upload the file again.'

export async function POST(request) {
  let data
  try {
    data = unseal((await request.json())?.data)
  } catch {
    data = null
  }
  if (!data) return noStore({ error: EXPIRED }, { status: 404 })

  try {
    return await exportFile(transfers(data))
  } catch (error) {
    return exportFailed(error)
  }
}

// The Python's token links, from a page loaded before this changed
export async function GET() {
  return noStore({ error: EXPIRED }, { status: 404 })
}
