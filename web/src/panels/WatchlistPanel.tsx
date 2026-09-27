import { useDrift, useQuotes, useSuggestions } from '../api/hooks'
import type { Quote, SuggestionView } from '../api/types'
import { Flash, Pill, Sparkline } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { price, signed, tone } from '../lib/format'
import { useTerminal } from '../state/store'

const REGIME_TONE = { 'TREND UP': 'up', 'TREND DN': 'down', RANGE: 'mid' } as const

function Row({ q, pending }: { q: Quote; pending?: SuggestionView }) {
  const active = useTerminal((s) => s.asset === q.asset)
  const setAsset = useTerminal((s) => s.setAsset)
  const live = useTerminal((s) => s.prices[q.asset])
  const last = live ?? q.last
  const hi = Math.max(q.day_high, last)
  const lo = Math.min(q.day_low, last)
  const ch = last - q.prev_close
  const meta = ASSET_META[q.asset]
  const pos = ((last - lo) / (hi - lo || 1)) * 100

  return (
    <button className={`tk ${active ? 'on' : ''}`} onClick={() => setAsset(q.asset)} title={meta.pair} aria-pressed={active}>
      <span className="id">
        <span className="sym">{meta.label}</span>
        <span className="nm">{meta.name}</span>
      </span>
      <Flash value={last} className="px">
        {price(q.asset, last)}
      </Flash>
      <span className={`rgl ${REGIME_TONE[q.regime]}`}>{q.regime}</span>
      <span className={`ch ${tone(ch)}`}>
        {signed(ch, meta.dp)}&nbsp;&nbsp;{signed((ch / q.prev_close) * 100)}%
      </span>
      <Sparkline values={[...q.sparkline.slice(0, -1), last]} />
      <span className="range">
        <span>L {price(q.asset, lo)}</span>
        <span className="rail">
          <i style={{ left: `calc(${pos.toFixed(1)}% - 1px)` }} />
        </span>
        <span>H {price(q.asset, hi)}</span>
      </span>
      {pending && (
        <span className="pend">
          PENDING <b className={pending.suggestion.direction === 'LONG' ? 'up' : 'down'}>{pending.suggestion.direction}</b> · CONF{' '}
          {pending.suggestion.confidence.toFixed(2)} · R:R {pending.risk_reward.toFixed(1)}
        </span>
      )}
    </button>
  )
}

export function WatchlistPanel({ hidden }: { hidden: boolean }) {
  const quotes = useQuotes()
  const suggestions = useSuggestions()
  const drift = useDrift()
  const setView = useTerminal((s) => s.setView)
  const pending = suggestions.data ?? []

  return (
    <Panel code="WL" title="Watchlist" hidden={hidden} meta={<span className="dim">1–4 SELECT</span>}>
      <div className="watch">
        <div className="wl-head">
          <span className="lbl">Asset · regime</span>
          <span className="lbl">Last · day</span>
        </div>
        <nav className="wl" aria-label="Watchlist">
          {quotes.isError && <p className="load-err">Couldn't load quotes: {String(quotes.error)}</p>}
          {quotes.data?.map((q) => (
            <Row key={q.asset} q={q} pending={pending.find((p) => p.suggestion.asset === q.asset)} />
          ))}
        </nav>
        <div className="glance">
          <button onClick={() => setView('SUGG')}>
            <span className="lbl">
              Queue <kbd>F4</kbd>
            </span>
            <span className="v">{pending.length} pending</span>
          </button>
          <button onClick={() => setView('DRIFT')}>
            <span className="lbl">
              Drift <kbd>F6</kbd>
            </span>
            <span className="v">
              {drift.data ? (
                <>
                  <Pill tone={drift.data.status === 'OK' ? 'ok' : drift.data.status === 'WATCH' ? 'watch' : 'drift'}>{drift.data.status}</Pill>
                  {signed(drift.data.z_score, 1)}σ
                </>
              ) : (
                '—'
              )}
            </span>
          </button>
        </div>
      </div>
    </Panel>
  )
}
