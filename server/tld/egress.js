// The TLD egress connector for queries that carry a JSON body, which is every
// query the TLD dashboard makes and anything else built on core/Tld. Sends,
// times out, unwraps. What to ask for is core/Tld/Queries.fs; what the answer
// means is the rest of core/Tld.
//
// These bodies carry arrays (columns, phone numbers, lead
// ids) that TLD reads from a JSON body. TLD takes that body on a GET, which
// fetch() refuses to send, so the request goes through node:https instead.
// Paced by rateLimit.js.
import https from 'node:https'
import http from 'node:http'

import { crmConfig, authHeaders } from '#tld/config.js'
import { takeToken } from '#tld/rateLimit.js'
import { unwrap } from '#generated/Tld/Rows.js'

const DEFAULT_TIMEOUT_MS = 30000        // most queries, the heavy reports pass their own

export class TldError extends Error {}

/*
 GET /api/egress/<path> with a JSON body. Resolves to the unwrapped rows, and
 rejects with a TldError whose message is safe to show on a page: it names
 the endpoint and the status, never the url, which carries nothing secret
 here but would if this ever moved to query string auth.
*/
export async function egress(path, body, options) {
  return unwrap(await egressRaw(path, body, options))
}

/*
 The same request, answered as TLD sent it. For reports, whose totals sit
 beside the rows and are lost by unwrapping; core/Tld reads these with
 unwrapResults.
*/
export async function egressRaw(path, body, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const config = crmConfig()
  if (!config.isConfigured) throw new TldError(`TLD is not configured: ${config.problems.join(' ')}`)

  const url = new URL(`${config.baseUrl}/api/egress/${String(path).replace(/^\/+/, '')}`)
  const payload = JSON.stringify(body ?? {})
  const transport = url.protocol === 'http:' ? http : https

  await takeToken()

  const text = await new Promise((resolve, reject) => {
    const request = transport.request(
      url,
      {
        method: 'GET',
        headers: {
          ...authHeaders(config),
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'Content-Length': Buffer.byteLength(payload),
        },
        timeout: timeoutMs,
      },
      (response) => {
        const chunks = []
        response.on('data', (chunk) => chunks.push(chunk))
        response.on('end', () => {
          const status = response.statusCode || 0
          if (status < 200 || status >= 300) {
            reject(new TldError(`${path} returned HTTP ${status}.`))
          } else {
            resolve(Buffer.concat(chunks).toString('utf8'))
          }
        })
      }
    )
    request.on('timeout', () => request.destroy(new TldError(`${path} timed out.`)))
    request.on('error', (cause) =>
      reject(cause instanceof TldError ? cause : new TldError(`${path} could not be reached.`))
    )
    request.end(payload)
  })

  try {
    return JSON.parse(text)
  } catch {
    throw new TldError(`${path} did not return JSON.`)
  }
}

// A core/Tld/Queries.fs query, { endpoint, body }, sent as is
export function send(query, options) {
  return egress(query.endpoint, query.body, options)
}

export function sendRaw(query, options) {
  return egressRaw(query.endpoint, query.body, options)
}

// Today in Eastern time, where the agents are, as YYYY-MM-DD for core/Tld/Dates.fs
export function todayEastern(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(now)
}

// Now in Eastern time as YYYY-MM-DD HH:MM:SS, the stamp the live board shows
export function nowEastern(now = new Date()) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/New_York',
      hourCycle: 'h23',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
      .formatToParts(now)
      .map((p) => [p.type, p.value])
  )
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}
