// The frame every export route shares: the date range, the download, and the
// error answers the page shows. Each route only says how to build its workbook.
import { rangeFrom, noStore, exportFile, exportFailed } from '#tld/dashboardData.js'

export class ExportProblem extends Error {}   // the person's mistake, answered 400 as written

export function exportRoute(build) {
  return async function GET(request) {
    const range = rangeFrom(request)
    if (range.error) return noStore({ error: range.error }, { status: 400 })

    try {
      const book = await build(range, new URL(request.url).searchParams)
      return await exportFile(book)
    } catch (error) {
      if (error instanceof ExportProblem) return noStore({ error: error.message }, { status: 400 })
      return exportFailed(error)
    }
  }
}
