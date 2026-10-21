// Excel for the TLD dashboard. Writing and reading a workbook is
// core/Tld/Excel.fs (through exceljs); what goes in one is core/Tld/Workbooks.fs.
// This only turns the bytes into a download and an upload into bytes, the
// parts that are HTTP.
import { write, read } from '#generated/Tld/Excel.js'

const XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

// A core/Tld/Workbooks.fs workbook as .xlsx bytes
export async function writeWorkbook(book) {
  return Buffer.from(await write(book))
}

// The active sheet of uploaded .xlsx bytes, as { header, records }
export function readFirstSheet(bytes) {
  return read(bytes)
}

export function xlsxResponse(bytes, filename) {
  return new Response(bytes, {
    headers: {
      'Content-Type': XLSX_TYPE,
      'Content-Disposition': `attachment; filename="${filename.replace(/"/g, '')}"; filename*=UTF-8''${encodeURIComponent(filename)}`,
      'Cache-Control': 'no-store, private',
    },
  })
}
