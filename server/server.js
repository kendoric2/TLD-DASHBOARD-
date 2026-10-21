// The iHealth Plans TLD dashboard. A plain Node server: the page from public/,
// and its data from server/routes, one file per /api path
// (/api/vendors/billed/export -> routes/vendors.billed.export.js). Every number
// is worked out in the F# core (core/Tld, compiled to generated/ by Fable);
// this file only moves requests and responses.
//
//   npm start            http://localhost:5050, opens the browser
//   PORT=8000            another port
//   NO_BROWSER=1         don't open the browser

import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { Readable } from 'node:stream'
import { exec } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const PUBLIC = path.join(ROOT, 'public')
const ROUTES = path.join(ROOT, 'server', 'routes')

loadEnv(path.join(ROOT, '.env'))

const PORT = Number(process.env.PORT || 5050)
const URL_BASE = `http://localhost:${PORT}`

const { crmConfig } = await import('#tld/config.js')

/*=======================================================
        .env
========================================================*/

// KEY=value lines; a value already in the environment wins
function loadEnv(file) {
  if (!fs.existsSync(file)) return
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (!match || process.env[match[1]] !== undefined) continue
    process.env[match[1]] = match[2].replace(/^(['"])(.*)\1$/, '$2')
  }
}

/*=======================================================
        THE PAGE AND ITS FILES
========================================================*/

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
}

function sendFile(res, file) {
  // Never outside public/, whatever the url says
  if (!file.startsWith(PUBLIC + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return sendText(res, 404, 'Not found')
  }
  res.writeHead(200, {
    'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream',
    'Cache-Control': 'no-cache',
  })
  fs.createReadStream(file).pipe(res)
}

function sendText(res, status, text) {
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' })
  res.end(text)
}

function sendJson(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
  res.end(JSON.stringify(body))
}

/*=======================================================
        THE DATA ROUTES
========================================================*/

const loaded = new Map()                // module file -> its exports, or null when there is none

async function routeFor(pathname) {
  const name = pathname.slice('/api/'.length)
  if (!/^[a-z_]+(\/[a-z_]+)*$/.test(name)) return null
  const file = path.join(ROUTES, `${name.replace(/\//g, '.')}.js`)
  if (!loaded.has(file)) {
    loaded.set(file, fs.existsSync(file) ? await import(`file://${file.replace(/\\/g, '/')}`) : null)
  }
  return loaded.get(file)
}

// Node's request as a web Request, which is what the route files take
function toRequest(req) {
  const hasBody = req.method !== 'GET' && req.method !== 'HEAD'
  return new Request(new URL(req.url, URL_BASE), {
    method: req.method,
    headers: req.headers,
    body: hasBody ? Readable.toWeb(req) : undefined,
    duplex: hasBody ? 'half' : undefined,
  })
}

async function sendResponse(res, response) {
  const headers = {}
  response.headers.forEach((value, key) => { headers[key] = value })
  res.writeHead(response.status, headers)
  if (!response.body) return res.end()
  Readable.fromWeb(response.body).pipe(res)
}

/*=======================================================
        THE SERVER
========================================================*/

async function handle(req, res) {
  const { pathname } = new URL(req.url, URL_BASE)

  if (pathname === '/' || pathname === '/index.html') return sendFile(res, path.join(PUBLIC, 'index.html'))
  if (pathname.startsWith('/static/')) return sendFile(res, path.join(PUBLIC, path.normalize(decodeURIComponent(pathname))))
  if (pathname === '/health') return sendJson(res, 200, { ok: true, live: crmConfig().isConfigured })

  if (pathname.startsWith('/api/')) {
    const route = await routeFor(pathname)
    if (!route) return sendJson(res, 404, { error: 'Not found' })
    const handler = route[req.method === 'HEAD' ? 'GET' : req.method]
    if (!handler) return sendJson(res, 405, { error: 'Method not allowed' })
    return sendResponse(res, await handler(toRequest(req)))
  }

  return sendText(res, 404, 'Not found')
}

const server = http.createServer((req, res) => {
  handle(req, res).catch((error) => {
    console.error(`${req.method} ${req.url}: ${error?.stack || error}`)
    if (!res.headersSent) sendJson(res, 500, { error: error?.message || 'Something went wrong.' })
    else res.destroy()
  })
})

// The cost report and a long vendor pull take minutes on TLD's side
server.requestTimeout = 15 * 60 * 1000
server.headersTimeout = 60 * 1000

server.listen(PORT, '127.0.0.1', () => {
  console.log(`\n  iHealth Plans dashboard  ->  ${URL_BASE}\n  (press CTRL+C to stop)\n`)

  const crm = crmConfig()
  if (!crm.isConfigured) {
    console.log(`  TLD is not connected: ${crm.problems.join(' ')}\n  Fill them in .env and restart.\n`)
  } else {
    warmCost()
  }

  if (!process.env.NO_BROWSER) openBrowser(URL_BASE)
})

// Today's cost report fetched once at start, so the first page view has it
async function warmCost() {
  try {
    const { GET } = await routeFor('/api/agent_cpa')
    await GET(new Request(`${URL_BASE}/api/agent_cpa?range=today`))
  } catch {
    // the page asks again when it loads
  }
}

function openBrowser(url) {
  const command =
    process.platform === 'win32' ? `start "" "${url}"` :
    process.platform === 'darwin' ? `open "${url}"` : `xdg-open "${url}"`
  exec(command, () => {})
}
