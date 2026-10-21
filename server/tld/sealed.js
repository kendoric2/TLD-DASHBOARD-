// A Transfer Check result the page can hand back for its Excel export without
// the server keeping it. The result carries a signature, and the export is
// built only from a result whose signature still matches, so a payroll file
// can never be built from numbers edited in the browser.
//
// The key is made fresh each time the server starts, so a check from before a
// restart reads as expired, as the old in-memory token did.

import crypto from 'node:crypto'

const KEY = crypto.randomBytes(32)

function sign(data) {
  return crypto.createHmac('sha256', KEY).update(JSON.stringify(data)).digest('hex')
}

// The result as sent to the page, with its signature
export function seal(data) {
  return { ...data, signature: sign(data) }
}

// The result handed back, without its signature, or null when it was changed or never signed here
export function unseal(posted) {
  if (!posted || typeof posted !== 'object' || typeof posted.signature !== 'string') return null
  const { signature, ...data } = posted
  const expected = Buffer.from(sign(data), 'hex')
  const given = Buffer.from(signature, 'hex')
  return given.length === expected.length && crypto.timingSafeEqual(given, expected) ? data : null
}
