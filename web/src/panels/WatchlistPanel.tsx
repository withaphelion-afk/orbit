import { useQuotes, useRegime, useSky } from '../api/hooks'
import type { Quote } from '../api/types'
import { Flash, Pill, QueryState, Sparkline } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, daysFrom, price, signed, tone, transitLabel } from '../lib/format'
import { useTerminal } from '../state/store'

const REGIME_TONE = { BULL: 'up', BEAR: 'down', CHOPPY: 'mid' } as const

function Row({ q }: { q: Quote }) {
  const active = useTerminal((s) => s.asset === q.asset)
  const setAsset = useTerminal((s) => s.setAsset)
  const live = useTerminal((s) => s.prices[q.asset])
  const liveSource = useTerminal((s) => s.priceSource[q.asset])
  const last = live ?? q.last
  const source = liveSource ?? q.source
  const hi = Math.max(q.day_high, last)
  const lo = Math.min(q.day_low, last)
  const ch = last - q.prev_close
  const meta = ASSET_META[q.asset]
  const pos = ((last - lo) / (hi - lo || 1)) * 100

  return (
    <button className={`tk ${active ? 'on' : ''}`} onClick={() => setAsset(q.asset)} title={`${meta.pair} · ${source === 'STORED' ? 'last stored close' : source === 'DELAYED' ? 'delayed quote' : 'live'}`} aria-pressed={active}>
      <span className="id">
        <span className="sym">{meta.label}</span>
        <span className="nm">{meta.name}</span>
        {source !== 'LIVE' && <span className="src">{source}</span>}
      </span>
      <Flash value={last} className="px">
        {price(q.asset, last)}
      </Flash>
      <span className={`rgl ${q.regime ? REGIME_TONE[q.regime] : 'dim'}`} title={q.regime_scope === 'SHARED' ? 'Shared BTC/ETH regime gate' : "Silver's own trend (same 50/200-day rule)"}>
        {q.regime ?? 'NO READING'}
        <span className="scope">{q.regime_scope === 'SHARED' ? ' · GATE' : ' · OWN TREND'}</span>
      </span>
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
    </button>
  )
}

export function WatchlistPanel({ hidden }: { hidden: boolean }) {
  const quotes = useQuotes()
  const regime = useRegime()
  const sky = useSky()
  const setView = useTerminal((s) => s.setView)
  const gate = regime.data?.find((r) => r.scope === 'SHARED')
  const next = (sky.data ?? [])
    .map((p) => p.next_event)
    .filter((e) => e !== null)
    .sort((a, b) => a.date.localeCompare(b.date))[0]

  return (
    <Panel code="WL" title="Watchlist" hidden={hidden}>
      <div className="watch">
        <div className="wl-head">
          <span className="lbl">Asset · regime</span>
          <span className="lbl">Last · day</span>
        </div>
        <nav className="wl" aria-label="Watchlist">
          <QueryState isPending={quotes.isPending} error={quotes.error} what="quotes" />
          {quotes.data?.map((q) => <Row key={q.asset} q={q} />)}
        </nav>
        <div className="glance">
          <button onClick={() => setView('SYS')} title="Shared BTC/ETH regime gate">
            <span className="lbl">Regime gate</span>
            <span className="v">
              {gate?.value ? <Pill tone={gate.value === 'BULL' ? 'ok' : gate.value === 'BEAR' ? 'drift' : 'watch'}>{gate.value}</Pill> : '—'}
              {gate?.since && <span className="since">since {day(gate.since)}</span>}
            </span>
          </button>
          <button onClick={() => setView('ASTRO')} title="Next transit (ASTRO, F7)">
            <span className="lbl">
              Next transit <kbd>F7</kbd>
            </span>
            <span className="v">
              {next ? (
                <>
                  <span className="astro-t">{transitLabel(next)}</span>
                  <span className="since">{daysFrom(next.date)}</span>
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
