// POST /api/logout: ends this device's session.
const { clearSession } = require('./_auth')

module.exports = async (req, res) => {
  clearSession(res)
  res.status(200).json({ ok: true })
}
