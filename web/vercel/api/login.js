// POST /api/login {username, password}: starts a 30-day session on this device.
const { body, checkLogin, setSession } = require('./_auth')

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ detail: 'POST only' })
  const { username = '', password = '' } = await body(req).catch(() => ({}))
  if (!checkLogin(username.trim(), password)) {
    await new Promise((r) => setTimeout(r, 800)) // slows down guessing
    return res.status(401).json({ detail: 'Wrong username or password.' })
  }
  setSession(res, username.trim())
  res.status(200).json({ user: username.trim() })
}
