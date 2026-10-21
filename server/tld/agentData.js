// The TLD pulls behind Agent Detail and its exports. Decided in
// core/Tld/AgentDetail.fs.
import { policyDetail, convertedLeads, agentCalls } from '#generated/Tld/Queries.js'
import { person, dispoNames, dispo } from '#generated/Tld/AgentDetail.js'
import { send } from '#tld/egress.js'

const KEEP_FOR_MS = 5 * 60 * 1000       // clicking between people reuses one pull of the range
const held = new Map()                  // `${start}|${end}` -> { at, promise }

/*
 The range's policies and the SEP lookup, side by side, held 5 minutes as the
 Python held them. SEP is a nice to have: if it fails the deals still show.
*/
function pullsFor(start, end) {
  const key = `${start}|${end}`
  const hit = held.get(key)
  if (hit && Date.now() - hit.at < KEEP_FOR_MS) return hit.promise

  const promise = Promise.all([
    send(policyDetail(start, end), { timeoutMs: 60000 }),
    send(convertedLeads(start, end), { timeoutMs: 120000 }).catch(() => []),
  ])
  held.set(key, { at: Date.now(), promise })
  promise.catch(() => held.delete(key))
  return promise
}

export async function agentDetailFor(start, end, agent, label) {
  const [policyRows, sepRows] = await pullsFor(start, end)
  return person(policyRows, sepRows, agent, label)
}

// converted name first, then as given; stop at the first that finds calls
export async function agentDispoFor(start, end, agent) {
  const searched = []
  let calls = []
  for (const name of dispoNames(agent)) {
    searched.push(name)
    calls = await send(agentCalls(start, end, name), { timeoutMs: 240000 })
    if (calls.length) break
  }
  return dispo(calls, searched)
}
