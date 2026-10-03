import { beforeEach, describe, expect, it } from 'vitest'
import { ApiError } from './http'
import { createStaticApi, patternKey } from './static'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const SRC = { dataRepo: 'o/data', codeRepo: 'o/code' }

/** Serves `map` as the data repo's site branch; `calls` records the file paths asked for. */
function files(map: Record<string, unknown>, status?: number) {
  const calls: string[] = []
  const fetcher = (async (input: RequestInfo | URL) => {
    const url = String(input)
    const key = decodeURIComponent(url.split('path=')[1] ?? '')
    calls.push(key)
    if (status) return new Response('', { status })
    return key in map ? json(map[key]) : new Response('not found', { status: 404 })
  }) as typeof fetch
  return { calls, fetcher }
}

// Tests run in Node, which has no localStorage: an in-memory one stands in.
function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  }
}

describe('createStaticApi', () => {
  beforeEach(() => {
    globalThis.localStorage = memoryStorage()
  })

  it('names pattern files like the Python snapshot does', () => {
    // python: orbit.snapshot.pattern_key('MARS:INGRESS:Aries|VAKRI')
    expect(patternKey('MARS:INGRESS:Aries|VAKRI')).toBe('4d4152533a494e47524553533a41726965737c56414b5249')
  })

  it('reads the published file for each endpoint', async () => {
    const { calls, fetcher } = files({ 'quotes.json': [], [`patterns/BTC/${patternKey('A:B')}.json`]: {} })
    const api = createStaticApi(SRC, fetcher)
    await api.quotes()
    await api.pattern('BTC', 'A:B')
    expect(calls).toEqual(['quotes.json', `patterns/BTC/${patternKey('A:B')}.json`])
  })

  it('turns a published error into the same ApiError the server would give', async () => {
    const { fetcher } = files({ 'drift.json': { __error: { status: 404, detail: 'No backtest yet.' } } })
    const err = await createStaticApi(SRC, fetcher).drift().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(404)
    expect(err.message).toBe('No backtest yet.')
  })

  it('serves the default transit window, and filters the full list for a range', async () => {
    const ev = (date: string) => ({ event: { date }, label: date, notable: [] })
    const { calls, fetcher } = files({
      'transits.json': [ev('2026-10-01T00:00:00Z')],
      'transits-all.json': [ev('2019-05-01T00:00:00Z'), ev('2020-06-15T12:00:00Z'), ev('2021-01-01T00:00:00Z')],
    })
    const api = createStaticApi(SRC, fetcher)
    expect(await api.transits()).toHaveLength(1)
    const ranged = await api.transits('2020-01-01', '2020-12-31T23:59:59Z')
    expect(ranged.map((t) => t.label)).toEqual(['2020-06-15T12:00:00Z'])
    expect(calls).toContain('transits-all.json')
  })

  it('builds an hourly window across a year boundary from compact rows', async () => {
    const { fetcher } = files({
      'hourly/BTC/2025.json': [['2025-12-31T22:00:00+00:00', 1, 2, 0.5, 1.5, 10], ['2025-12-31T23:00:00+00:00', 1, 2, 0.5, 1.6, 11]],
      'hourly/BTC/2026.json': [['2026-01-01T00:00:00+00:00', 1, 2, 0.5, 1.7, 12], ['2026-01-01T05:00:00+00:00', 1, 2, 0.5, 1.8, 13]],
    })
    const bars = await createStaticApi(SRC, fetcher).intraday('BTC', '2026-01-01T00:00:00Z', 1, 1)
    expect(bars.map((b) => b.close)).toEqual([1.6, 1.7])
    expect(bars[0]).toMatchObject({ asset: 'BTC', open: 1, volume: 11 })
  })

  it('marks a published LIVE runner as STALE once its last cycle is too old', async () => {
    const old = new Date(Date.now() - 5 * 3_600_000).toISOString()
    const { fetcher } = files({ 'system.json': { runner: { state: 'LIVE', last_cycle_finished_at: old, interval_seconds: 3600 } } })
    expect((await createStaticApi(SRC, fetcher).system()).runner.state).toBe('STALE')
  })

  it('hides a suggestion you just decided until the snapshot catches up', async () => {
    const { fetcher } = files({ 'suggestions.json': [{ id: 's1' }, { id: 's2' }] })
    localStorage.setItem('orbit.decided', JSON.stringify({ s1: Date.now() }))
    const ids = (await createStaticApi(SRC, fetcher).suggestions()).map((s) => s.id)
    expect(ids).toEqual(['s2'])
  })

  it('asks GitHub once a minute at most for the same file', async () => {
    const { calls, fetcher } = files({ 'quotes.json': [] })
    const api = createStaticApi(SRC, fetcher)
    await api.quotes()
    await api.quotes()
    expect(calls).toEqual(['quotes.json'])
  })

  it('reads through the login service on the site, never GitHub directly', async () => {
    const urls: string[] = []
    const fetcher = (async (input: RequestInfo | URL) => {
      urls.push(String(input))
      return json([])
    }) as typeof fetch
    await createStaticApi(SRC, fetcher).quotes()
    expect(urls).toEqual(['/api/file?path=quotes.json'])
  })

  it('reports a logged-out session as 401', async () => {
    const { fetcher } = files({}, 401)
    const err = await createStaticApi(SRC, fetcher).quotes().catch((e) => e)
    expect(err.status).toBe(401)
  })
})
