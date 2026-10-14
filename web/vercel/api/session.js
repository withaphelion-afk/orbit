// GET /api/session: who is logged in on this device (401 if nobody).
const { isGuest, session } = require('./_auth')

module.exports = async (req, res) => {
  const user = session(req)
  if (!user) return res.status(401).json({ detail: 'Not logged in.' })
  res.status(200).json({ user, guest: isGuest(user) })
}
