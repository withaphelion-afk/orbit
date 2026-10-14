// POST /api/guest: a read-only session for a visitor without the login (1 day). Off when ORBIT_GUEST_LOGIN is "0".
const { GUEST, GUEST_DAYS, guestEnabled, setSession } = require('./_auth')

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ detail: 'POST only' })
  if (!guestEnabled()) return res.status(403).json({ detail: 'Guest access is turned off.' })
  setSession(res, GUEST, GUEST_DAYS)
  res.status(200).json({ user: GUEST, guest: true })
}
