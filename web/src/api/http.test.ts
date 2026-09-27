import { describe, expect, it } from 'vitest'
import { ApiError, createApi } from './http'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function recorder(response: () => Response | Promise<Response>) {
  const calls: string[] = []
  const fetcher = (async (input: RequestInfo | URL) => {
    calls.push(String(input))
    return response()
  }) as typeof fetch
  return { calls, fetcher }
}

describe('createApi', () => {
  it('encodes pattern ids, which contain colons', async () => {
    const { calls, fetcher } = recorder(() => json({}))
    await createApi('', fetcher).pattern('BTC', 'MARS:INGRESS:Aries')
    expect(calls).toEqual(['/api/playbook/BTC/patterns/MARS%3AINGRESS%3AAries'])
  })

  it('passes the transit window as from/to', async () => {
    const { calls, fetcher } = recorder(() => json([]))
    await createApi('http://api.test', fetcher).transits('2020-01-01', '2021-01-01')
    expect(calls).toEqual(['http://api.test/api/transits?from=2020-01-01&to=2021-01-01'])
  })

  it("surfaces the server's own explanation on errors", async () => {
    const { fetcher } = recorder(() => json({ detail: "The backtest layer isn't built yet." }, 404))
    const err = await createApi('', fetcher).drift().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(404)
    expect(err.message).toBe("The backtest layer isn't built yet.")
  })

  it('explains how to start the API when it is unreachable', async () => {
    const fetcher = (async () => {
      throw new TypeError('Failed to fetch')
    }) as typeof fetch
    const err = await createApi('', fetcher).system().catch((e) => e)
    expect(err.status).toBe(0)
    expect(err.message).toMatch(/python -m orbit\.api/)
  })
})
