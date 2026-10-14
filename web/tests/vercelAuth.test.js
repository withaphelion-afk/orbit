import { createRequire } from 'node:module'
import { beforeEach, describe, expect, it } from 'vitest'

// The login service's functions are CommonJS (web/vercel/api); they run on Vercel, so they are tested here with fake requests.
const require = createRequire(import.meta.url)
const env = process.env
const auth = require('../vercel/api/_auth.js')
const guest = require('../vercel/api/guest.js')
const dispatch = require('../vercel/api/dispatch.js')
const file = require('../vercel/api/file.js')
const sessionRoute = require('../vercel/api/session.js')

function fakeRes() {
  const r = { code: 200, body: undefined, headers: {} }
  r.status = (n) => ((r.code = n), r)
  r.json = (b) => ((r.body = b), r)
  r.end = () => r
  r.send = (b) => ((r.body = b), r)
  r.setHeader = (k, v) => void (r.headers[k] = v)
  return r
}
/** A request carrying the cookie a previous response set. */
const withCookie = (res, extra = {}) => ({
  headers: { cookie: res.headers['Set-Cookie'].split(';')[0] },
  ...extra,
})

describe('guest login', () => {
  beforeEach(() => {
    env.ORBIT_GITHUB_TOKEN = 't'
    env.ORBIT_LOGIN_USER = 'owner'
    env.ORBIT_LOGIN_PASSWORD = 'pw'
    delete env.ORBIT_GUEST_LOGIN
  })

  it('starts a read-only session that /api/session reports as a guest', async () => {
    const res = fakeRes()
    await guest({ method: 'POST' }, res)
    expect(res.code).toBe(200)
    const s = fakeRes()
    await sessionRoute(withCookie(res), s)
    expect(s.body).toEqual({ user: 'guest', guest: true })
  })

  it('is refused when ORBIT_GUEST_LOGIN is 0', async () => {
    env.ORBIT_GUEST_LOGIN = '0'
    const res = fakeRes()
    await guest({ method: 'POST' }, res)
    expect(res.code).toBe(403)
    expect(res.headers['Set-Cookie']).toBeUndefined()
  })

  it("can't start workflows or read the journal, but can read other files", async () => {
    const g = fakeRes()
    await guest({ method: 'POST' }, g)

    const d = fakeRes()
    await dispatch(withCookie(g, { method: 'POST', body: { workflow: 'analysis.yml' } }), d)
    expect(d.code).toBe(403)

    const j = fakeRes()
    await file(withCookie(g, { query: { path: 'journal.json' } }), j)
    expect(j.code).toBe(403)
  })

  it('does not let the owner session be mistaken for a guest, and refuses "guest" as a username', () => {
    expect(auth.checkLogin('guest', 'pw')).toBe(false)
    expect(auth.checkLogin('Guest', 'pw')).toBe(false)
    expect(auth.checkLogin('owner', 'pw')).toBe(true)
    const res = fakeRes()
    auth.setSession(res, 'owner')
    expect(auth.requireSession(withCookie(res), fakeRes(), { owner: true })).toBe(true)
  })

  it('needs a session for everything else', () => {
    const res = fakeRes()
    expect(auth.requireSession({ headers: {} }, res)).toBe(false)
    expect(res.code).toBe(401)
  })
})
