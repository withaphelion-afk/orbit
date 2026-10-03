import { lazy, Suspense, useMemo } from 'react'
import { useCandles, useComponents, useSignals, useSuggestions, useTransits } from '../api/hooks'
import type { TransitView } from '../api/types'
import { QueryState, Seg } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSETS, ASSET_META, TV_INTERVALS } from '../config'
import { useTerminal, type ChartMode } from '../state/store'
import { TradingViewChart } from './chart/TradingViewChart'

// The charting library is only needed for Orbit's own chart, so the LIVE (TradingView) default doesn't download it.
const OrbitChart = lazy(() => import('./chart/OrbitChart').then((m) => ({ default: m.OrbitChart })))

const MODES: { label: string; value: ChartMode }[] = [
  { label: 'LIVE', value: 'LIVE' },
  { label: 'ORBIT', value: 'ORBIT' },
]
const SLOW = new Set(['JUPITER', 'SATURN', 'RAHU', 'KETU'])
const ALWAYS = new Set(['STATION_RETROGRADE', 'STATION_DIRECT', 'SOLAR_ECLIPSE', 'LUNAR_ECLIPSE'])

export function ChartPanel({ hidden }: { hidden: boolean }) {
  const asset = useTerminal((s) => s.asset)
  const setAsset = useTerminal((s) => s.setAsset)
  const mode = useTerminal((s) => s.chartMode)
  const setMode = useTerminal((s) => s.setChartMode)
  const interval = useTerminal((s) => s.tvInterval)
  const setInterval = useTerminal((s) => s.setTvInterval)
  const meta = ASSET_META[asset]

  return (
    <Panel
      code="GP"
      hidden={hidden}
      title={`${meta.name} · ${mode === 'LIVE' ? 'TradingView live' : 'Orbit daily, full history'}`}
      meta={
        <>
          <Seg label="Asset" value={asset} onChange={setAsset} options={ASSETS.map((a) => ({ label: ASSET_META[a].label, value: a }))} />
          {mode === 'LIVE' ? (
            <Seg label="Interval" value={interval} onChange={setInterval} options={TV_INTERVALS.map((i) => ({ label: i.label, value: i.value }))} />
          ) : (
            <Seg label="Interval" value="D" onChange={() => {}} options={[{ label: '1D', value: 'D' }]} />
          )}
          <Seg label="Chart source" value={mode} onChange={setMode} options={MODES} />
        </>
      }
    >
      {mode === 'LIVE' ? (
        <>
          <TradingViewChart symbol={meta.tvSymbol} interval={interval} />
          <a className="tv-credit" href={`https://www.tradingview.com/symbols/${meta.tvSymbol.replace(':', '-')}/`} target="_blank" rel="noopener noreferrer nofollow">
            {meta.tvSymbol} chart by TradingView
          </a>
        </>
      ) : (
        <OrbitChartData />
      )}
    </Panel>
  )
}

/** Which Vedic events to mark: every station (vakri / margi) and eclipse, the slow
 * grahas' rashi changes (Guru, Shani, Rahu, Ketu), and anything the playbook rates
 * weak or better for this asset. Everything else (hundreds of drishti, yuti and
 * nakshatra changes a year) would bury the chart. */
function markable(v: TransitView, asset: string) {
  const e = v.event
  if (v.notable.some((n) => n.asset === asset)) return true
  if (ALWAYS.has(e.event_type)) return e.planet !== 'RAHU' && e.planet !== 'KETU'
  return e.event_type === 'INGRESS' && SLOW.has(e.planet) && e.planet !== 'KETU' // Ketu mirrors Rahu
}

function OrbitChartData() {
  const asset = useTerminal((s) => s.asset)
  const candles = useCandles(asset)
  const signals = useSignals(asset)
  const first = candles.data?.[0]?.timestamp
  // End at today's date, not "now": a timestamp that changes every render would refetch in a loop.
  const transits = useTransits(first, `${new Date().toISOString().slice(0, 10)}T23:59:59Z`)
  const { components } = useComponents()
  const suggestions = useSuggestions(!!components?.strategy)
  const marks = useMemo(() => (transits.data ?? []).filter((v) => markable(v, asset)), [transits.data, asset])

  if (!candles.data) return <QueryState isPending={candles.isPending} error={candles.error} what="candles" />
  return (
    <Suspense fallback={<QueryState isPending error={null} what="chart" />}>
      <OrbitChart
        asset={asset}
        candles={candles.data}
        signals={signals.data ?? []}
        transits={marks}
        pending={suggestions.data?.find((s) => s.suggestion.asset === asset)}
      />
    </Suspense>
  )
}
