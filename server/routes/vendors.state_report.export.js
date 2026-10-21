// State Report export, /api/vendors/state_report/export: best and
// worst customer states, and the vendor behind each. Always every vendor.

import { stateReport } from '#generated/Tld/Workbooks.js'
import { exportRoute } from '#tld/exportRoute.js'
import { stateReportFor } from '#tld/vendorData.js'

export const GET = exportRoute(async (range) => stateReport(range.start, range.end, await stateReportFor(range.start, range.end)))
