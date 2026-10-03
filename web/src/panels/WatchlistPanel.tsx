import { Activity, Orbit } from 'lucide-react'
import { useComponents, useQuotes, useRegime, useSky, useSuggestions } from '../api/hooks'
import type { Quote, SuggestionView } from '../api/types'
import { Empty, Flash, QueryState, Sparkline, StatCard, StatGrid } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSETS, ASSET_META } from '../config'
import { day, daysFrom, price, signed, tone, transitLabel } from '../lib/format'
import { useTerminal } from '../state/store'

const REGIME_TONE = { BULL: 'up', BEAR: 'down', CHOPPY: 'mid' } as const
const GATE_TONE = { BULL: 'up', BEAR: 'down', CHOPPY: 'warn' } as const
const SOURCE_NOTE = { LIVE: 'live', DELAYED: 'delayed quote', STORED: 'last stored close' } as const

function Row({ q, pending }: { q: Quote; pending?: SuggestionView }) {
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
  const key = ASSETS.indexOf(q.asset) + 1

  return (
    <button className={`wl-row ${active ? 'on' : ''}`} onClick={() => setAsset(q.asset)} title={`${meta.pair} · ${SOURCE_NOTE[source]}`} aria-pressed={active}>
      <kbd className="wl-key" title={`Press ${key} to select ${meta.label}`}>
        {key}
      </kbd>
      <span className="wl-id">
        <b className="wl-sym">{meta.label}</b>
        <span className="wl-nm">{meta.name}</span>
        {source !== 'LIVE' && <span className="wl-src">{source}</span>}
      </span>
      <Flash value={last} className="wl-px">
        {price(q.asset, last)}
      </Flash>
      <span className={`wl-rg ${q.regime ? REGIME_TONE[q.regime] : 'dim'}`} title={q.regime_scope === 'SHARED' ? 'Shared BTC/ETH regime gate' : "Silver's own trend (same 50/200-day rule)"}>
        <i />
        {q.regime ?? 'NO READING'}
        <span className="wl-scope">{q.regime_scope === 'SHARED' ? ' · GATE' : ' · OWN TREND'}</span>
      </span>
      <span className={`wl-ch ${tone(ch)}`} title="Change since the previous close">
        {signed(ch, meta.dp)}
        <span>{signed((ch / q.prev_close) * 100)}%</span>
      </span>
      <Sparkline values={[...q.sparkline.slice(0, -1), last]} height={24} />
      <span className="wl-range" title="Day range: low, last price, high">
        <span>L {price(q.asset, lo)}</span>
        <span className="wl-rail">
          <i style={{ left: `${pos.toFixed(1)}%` }} />
        </span>
        <span>H {price(q.asset, hi)}</span>
      </span>
      {pending && (
        <span className="wl-pend" title="A suggestion for this asset is waiting for your decision (SUGG, F4)">
          PENDING <b className={pending.suggestion.direction === 'LONG' ? 'up' : 'down'}>{pending.suggestion.direction}</b>
          <span>· CONF {pending.suggestion.confidence.toFixed(2)}</span>
          <span>· R:R {pending.risk_reward.toFixed(1)}</span>
        </span>
      )}
    </button>
  )
}

export function WatchlistPanel({ hidden }: { hidden: boolean }) {
  const quotes = useQuotes()
  const regime = useRegime()
  const sky = useSky()
  const { components } = useComponents()
  const suggestions = useSuggestions(!!components?.strategy)
  const setView = useTerminal((s) => s.setView)
  const gate = regime.data?.find((r) => r.scope === 'SHARED')
  const next = (sky.data ?? [])
    .map((p) => p.next_event)
    .filter((e) => e !== null)
    .sort((a, b) => a.date.localeCompare(b.date))[0]

  return (
    <Panel code="WL" title="Watchlist" description="Click an instrument or press 1–4 to chart it." hidden={hidden}>
      <div className="watch">
        <div className="wl-head">
          <span className="lbl">Asset · regime</span>
          <span className="lbl">Last · day</span>
        </div>
        <nav className="wl" aria-label="Watchlist">
          <QueryState isPending={quotes.isPending} error={quotes.error} what="quotes" />
          {quotes.data?.length === 0 && <Empty title="NO QUOTES">The API returned no instruments.</Empty>}
          {quotes.data?.map((q) => (
            <Row key={q.asset} q={q} pending={suggestions.data?.find((s) => s.suggestion.asset === q.asset)} />
          ))}
        </nav>
        <StatGrid>
          <button className="wl-tile" onClick={() => setView('SYS')} title="Shared BTC/ETH regime gate (SYS, F8)">
            <StatCard
              label="Regime gate"
              value={gate?.value ?? '—'}
              tone={gate?.value ? GATE_TONE[gate.value] : 'dim'}
              icon={<Activity size={15} strokeWidth={1.75} />}
              caption={
                <span className="wl-cap">
                  <span>{gate?.since ? `since ${day(gate.since)}` : ''}</span>
                  <kbd>F8</kbd>
                </span>
              }
            />
          </button>
          <button className="wl-tile astro" onClick={() => setView('ASTRO')} title="Next transit (ASTRO, F7)">
            <StatCard
              label="Next transit"
              value={next ? transitLabel(next) : '—'}
              tone={next ? 'astro' : 'dim'}
              icon={<Orbit size={15} strokeWidth={1.75} />}
              caption={
                <span className="wl-cap">
                  <span>{next ? `${daysFrom(next.date)} · ${day(next.date)}` : ''}</span>
                  <kbd>F7</kbd>
                </span>
              }
            />
          </button>
        </StatGrid>
      </div>
    </Panel>
  )
}
