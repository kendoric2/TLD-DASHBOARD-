// TLD credentials, from .env (TLD_BASE_URL, TLD_API_ID, TLD_API_KEY). Read on
// every call so a changed .env needs only a restart, never a rebuild.

export function crmConfig() {
  const raw = String(process.env.TLD_BASE_URL || '').trim()
  const apiId = String(process.env.TLD_API_ID || '').trim()
  const apiKey = String(process.env.TLD_API_KEY || '').trim()

  const problems = []
  let baseUrl = null
  if (!raw) problems.push('TLD_BASE_URL is not set.')
  else {
    try {
      const url = new URL(raw)
      const local = url.hostname === 'localhost' || url.hostname === '127.0.0.1'
      if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) problems.push('TLD_BASE_URL must be https.')
      else baseUrl = `${url.origin}${url.pathname}`.replace(/\/+$/, '')
    } catch {
      problems.push('TLD_BASE_URL is not a valid url.')
    }
  }
  if (!apiId) problems.push('TLD_API_ID is not set.')
  if (!apiKey) problems.push('TLD_API_KEY is not set.')

  return { label: 'TLD', baseUrl, apiId, apiKey, isConfigured: problems.length === 0, problems }
}

export function authHeaders(config) {
  if (!config.isConfigured) throw new Error(`TLD is not configured: ${config.problems.join(' ')}`)
  return { 'tld-api-id': config.apiId, 'tld-api-key': config.apiKey }
}
