import type { Asset } from '../api/types'
import { ASSETS, ASSET_META } from '../config'

export type View = 'HELP' | 'MON' | 'GP' | 'SUGG' | 'JRNL' | 'DRIFT' | 'ASTRO' | 'SYS' | 'ALRT'

/** Terminal functions, in F-key order. `label` is the name in the navigation bar. */
export const FUNCTIONS: { code: View; key: string; label: string; desc: string }[] = [
  { code: 'HELP', key: 'F1', label: 'Help', desc: 'Commands and keys' },
  { code: 'MON', key: 'F2', label: 'Monitor', desc: 'Monitor: chart with the watchlist' },
  { code: 'GP', key: 'F3', label: 'Chart', desc: 'Price chart for the active asset' },
  { code: 'SUGG', key: 'F4', label: 'Suggestions', desc: 'RSI divergence suggestions awaiting your decision' },
  { code: 'JRNL', key: 'F5', label: 'Journal', desc: 'Trade journal' },
  { code: 'DRIFT', key: 'F6', label: 'Drift', desc: 'Backtest, feedback loop, and live vs backtest drift' },
  { code: 'ASTRO', key: 'F7', label: 'Astro', desc: 'Vedic sky, events, playbook and model (research)' },
  { code: 'SYS', key: 'F8', label: 'System', desc: 'Runner, feeds, alerts and config' },
  { code: 'ALRT', key: 'F9', label: 'Alerts', desc: 'Divergence alerts on 1H, 4H, 1D and 1W, with ✓/✗ to teach the model' },
]

const VIEW_CODES = new Set<string>(FUNCTIONS.map((f) => f.code))

/** Every token that names an asset: its code plus its terminal label (SILVER -> XAG). */
const ASSET_TOKENS = new Map<string, Asset>(ASSETS.flatMap((a) => [[a, a], [ASSET_META[a].label, a]] as [string, Asset][]))

export type Parsed = { asset?: Asset; view?: View } | { error: string }

/**
 * Parses a command line such as "SOL GP", "xag drift <GO>" or "SUGG".
 * Returns null for blank input.
 */
export function parseCommand(input: string): Parsed | null {
  const tokens = input
    .toUpperCase()
    .replace(/<?GO>?\s*$/, '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (!tokens.length) return null
  const out: { asset?: Asset; view?: View } = {}
  for (const t of tokens) {
    const asset = ASSET_TOKENS.get(t)
    if (asset) out.asset = asset
    else if (VIEW_CODES.has(t)) out.view = t as View
    else return { error: `UNKNOWN COMMAND "${t}". TYPE HELP` }
  }
  return out
}

/** Instruments matching a search, by code, label, name or pair (case-insensitive); all of them for a blank query. */
export function findInstruments(query: string): Asset[] {
  const q = query.trim().toLowerCase()
  if (!q) return ASSETS
  return ASSETS.filter((a) => {
    const m = ASSET_META[a]
    return [a, m.label, m.name, m.pair].some((s) => s.toLowerCase().includes(q))
  })
}
