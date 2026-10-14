// Shared by Orbit's Vercel functions: the login check and the signed session cookie.
// Files starting with "_" are not served as routes by Vercel.
const crypto = require('node:crypto')

const COOKIE = 'orbit_session'
const DAYS = 30
const GUEST = 'guest' // the session name of a guest; login.js refuses it as a username
const GUEST_DAYS = 1
const env = (k) => (process.env[k] || '').trim()

function secret() {
  // A signing key derived from the server-only token, so no extra setting is needed; changing the token logs everyone out.
  return crypto.createHash('sha256').update(`orbit-session|${env('ORBIT_GITHUB_TOKEN')}|${env('ORBIT_LOGIN_PASSWORD')}`).digest()
}

function sign(payload) {
  return crypto.createHmac('sha256', secret()).update(payload).digest('base64url')
}

function cookies(req) {
  const out = {}
  for (const part of (req.headers.cookie || '').split(';')) {
    const i = part.indexOf('=')
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim())
  }
  return out
}

/** The logged-in user, or null. */
function session(req) {
  const raw = cookies(req)[COOKIE]
  if (!raw) return null
  const [user, exp, mac] = raw.split('.')
  if (!user || !exp || !mac) return null
  const want = sign(`${user}.${exp}`)
  if (want.length !== mac.length || !crypto.timingSafeEqual(Buffer.from(want), Buffer.from(mac))) return null
  if (Number(exp) < Date.now() / 1000) return null
  return user
}

function setSession(res, user, days = DAYS) {
  const exp = Math.floor(Date.now() / 1000) + days * 86400
  const value = `${user}.${exp}.${sign(`${user}.${exp}`)}`
  res.setHeader('Set-Cookie', `${COOKIE}=${encodeURIComponent(value)}; Path=/; Max-Age=${days * 86400}; HttpOnly; Secure; SameSite=Lax`)
}

const isGuest = (user) => user === GUEST

/** Guest login is on unless the ORBIT_GUEST_LOGIN variable is "0". */
const guestEnabled = () => env('ORBIT_GUEST_LOGIN') !== '0'

function clearSession(res) {
  res.setHeader('Set-Cookie', `${COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`)
}

function same(a, b) {
  const x = Buffer.from(String(a))
  const y = Buffer.from(String(b))
  return x.length === y.length && crypto.timingSafeEqual(x, y)
}

function checkLogin(user, pass) {
  return !isGuest(user.toLowerCase()) && !!env('ORBIT_LOGIN_USER') && same(user, env('ORBIT_LOGIN_USER')) && same(pass, env('ORBIT_LOGIN_PASSWORD'))
}

/** A logged-in user; with `owner`, a guest is refused (guests can look, not act). */
function requireSession(req, res, { owner = false } = {}) {
  const user = session(req)
  if (!user) {
    res.status(401).json({ detail: 'Log in to see Orbit.' })
    return false
  }
  if (owner && isGuest(user)) {
    res.status(403).json({ detail: 'Guests can look but not act. Log in to do this.' })
    return false
  }
  return true
}

async function body(req) {
  if (req.body && typeof req.body === 'object') return req.body
  if (typeof req.body === 'string') return JSON.parse(req.body || '{}')
  const chunks = []
  for await (const c of req) chunks.push(c)
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')
}

const github = (path, init = {}) =>
  fetch(`https://api.github.com${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${env('ORBIT_GITHUB_TOKEN')}`, 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'orbit-web', ...(init.headers || {}) },
  })

module.exports = { env, session, setSession, clearSession, checkLogin, requireSession, body, github, GUEST, GUEST_DAYS, isGuest, guestEnabled }
