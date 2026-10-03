// POST /api/dispatch {workflow, inputs}: starts one of Orbit's workflows (analysis, decide, label) with the server's token.
const { body, env, github, requireSession } = require('./_auth')

const ALLOWED = new Set(['analysis.yml', 'decide.yml', 'label.yml'])

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ detail: 'POST only' })
  if (!requireSession(req, res)) return
  const { workflow, inputs = {} } = await body(req).catch(() => ({}))
  if (!ALLOWED.has(workflow)) return res.status(400).json({ detail: 'Unknown workflow.' })
  const r = await github(`/repos/${env('ORBIT_CODE_REPO')}/actions/workflows/${workflow}/dispatches`, {
    method: 'POST',
    headers: { Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: 'main', inputs }),
  })
  if (r.status !== 204) {
    return res.status(502).json({ detail: `GitHub answered ${r.status} starting ${workflow}: ${(await r.text()).slice(0, 200)}` })
  }
  res.status(204).end()
}
