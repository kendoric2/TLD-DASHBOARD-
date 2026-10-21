// The Transfer Check, /api/transfer_check. Upload a DialedIN
// export (CallDetails or BlindTransfer, CSV or Excel) or, with mode=list, the
// fronters' own list; every transfer is matched to its TLD lead, call and
// policies. Decided in core/Tld/TransferCheck.fs.
//
// The result comes back signed (lib/tld/sealed.js) so the page can hand it to
// the Excel export without the server keeping it.

import { runTransferCheck, readUpload, CheckError } from '#tld/transferCheck.js'
import { seal } from '#tld/sealed.js'
import { nowEastern } from '#tld/egress.js'
import { noStore } from '#tld/dashboardData.js'

const MAX_BYTES = 25 * 1024 * 1024      // the Python's limit; a week's file is well under 1 MB

export async function POST(request) {
  const form = await request.formData()
  const file = form.get('file')
  if (!file || typeof file === 'string' || !file.name) {
    return noStore({ error: 'Choose the DialedIN export file first.' }, { status: 400 })
  }
  if (file.size > MAX_BYTES) return noStore({ error: 'That file is too large.' }, { status: 400 })

  try {
    const data = await runTransferCheck({
      table: await readUpload(file),
      phoneList: form.get('mode') === 'list',
      start: String(form.get('start') || ''),
      end: String(form.get('end') || ''),
    })
    return noStore(seal({ ...data, checked_at: nowEastern().slice(0, 16) }))
  } catch (error) {
    if (error instanceof CheckError) return noStore({ error: error.message }, { status: 400 })
    return noStore({ error: `Transfer check failed: ${error.message}` }, { status: 500 })
  }
}
