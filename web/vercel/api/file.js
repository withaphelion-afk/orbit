// GET /api/file?path=quotes.json: one published snapshot file from the private data repo, read with the server's token.
const { env, github, isGuest, requireSession, session } = require('./_auth')

// Your own decisions and notes: not shown to guests.
const OWNER_ONLY = new Set(['journal.json'])

module.exports = async (req, res) => {
  if (!requireSession(req, res)) return
  const path = String(req.query.path || '')
  if (isGuest(session(req)) && OWNER_ONLY.has(path)) return res.status(403).json({ detail: 'The journal is private. Log in to see it.' })
  if (!/^[A-Za-z0-9_\-./]+$/.test(path) || path.includes('..')) return res.status(400).json({ detail: 'Bad path.' })
  const r = await github(`/repos/${env('ORBIT_DATA_REPO')}/contents/${path}?ref=site`, { headers: { Accept: 'application/vnd.github.raw+json' } })
  if (r.status === 404) return res.status(404).json({ detail: 'Not published yet. The next GitHub Actions run publishes it (hourly).' })
  if (!r.ok) return res.status(502).json({ detail: `GitHub answered ${r.status} reading ${path}. The server's GitHub token may be missing a permission.` })
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'private, max-age=30')
  res.status(200).send(await r.text())
}
