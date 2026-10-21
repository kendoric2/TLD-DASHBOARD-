// TLD's rate limit is a token bucket: 5 requests a second, refilling against a
// burst of 50. Every request to TLD takes a token first, so a big pull waits
// instead of being refused. Only waits when the bucket is empty.

const RATE_PER_SECOND = 5
const BURST_CAPACITY = 50

let tokens = BURST_CAPACITY
let lastRefill = Date.now()

function refill() {
  const now = Date.now()
  tokens = Math.min(BURST_CAPACITY, tokens + ((now - lastRefill) / 1000) * RATE_PER_SECOND)
  lastRefill = now
}

export async function takeToken() {
  refill()
  if (tokens < 1) {
    await new Promise((resume) => setTimeout(resume, Math.ceil(((1 - tokens) / RATE_PER_SECOND) * 1000)))
    refill()
  }
  tokens -= 1
}
