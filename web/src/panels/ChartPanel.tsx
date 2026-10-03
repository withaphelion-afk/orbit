import { lazy, Suspense } from 'react'
import { useComponents, useSuggestions } from '../api/hooks'
import type { Timeframe } from '../api/types'
import { QueryState, Seg } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META, TV_INTERVALS } from '../config'
import { useTerminal, type ChartMode } from '../state/store'
import { TradingViewChart } from './chart/TradingViewChart'

// The charting library is only needed for Orbit's own chart, so the LIVE (TradingView) default doesn't download it.
const OrbitChart = lazy(() => import('./chart/OrbitChart').then((m) => ({ default: m.OrbitChart })))

const MODES: { label: string; value: ChartMode }[] = [
  { label: 'LIVE', value: 'LIVE' },
  { label: 'ORBIT', value: 'ORBIT' },
]

const TF_OF: Record<string, Timeframe> = { '60': '1h', '240': '4h', D: '1d', W: '1w' }

export function ChartPanel({ hidden }: { hidden: boolean }) {
  const asset = useTerminal((s) => s.asset)
  const mode = useTerminal((s) => s.chartMode)
  const setMode = useTerminal((s) => s.setChartMode)
  const interval = useTerminal((s) => s.tvInterval)
  const setInterval = useTerminal((s) => s.setTvInterval)
  const meta = ASSET_META[asset]
  const live = mode === 'LIVE'
  const tf = TF_OF[interval] ?? '1d'

  return (
    <Panel
      code="GP"
      hidden={hidden}
      title={`${meta.name} · ${live ? 'TradingView live' : 'Orbit divergences'}`}
      description={
        live
          ? `${meta.pair} streamed live by TradingView, with its RSI(14) under price; switch to ORBIT for Orbit's own divergence detection, scores and your ✓/✗.`
          : `${meta.pair} with RSI(14), every divergence Orbit finds (solid once confirmed, dashed while forming), the learned model's score, and ✓/✗ to teach it.`
      }
      tools={
        <>
          <div className="gp-tool" title="Bar interval, for both charts">
            <span className="gp-tool-lbl">Interval</span>
            <Seg label="Interval" value={interval} onChange={setInterval} options={TV_INTERVALS.map((i) => ({ label: i.label, value: i.value }))} />
          </div>
          <div className="gp-tool gp-src" title="LIVE: TradingView's streamed chart with its RSI. ORBIT: Orbit's live divergence chart.">
            <span className="gp-tool-lbl">Source</span>
            <Seg label="Chart source" value={mode} onChange={setMode} options={MODES} />
          </div>
        </>
      }
    >
      {live ? <TradingViewChart symbol={meta.tvSymbol} interval={interval} /> : <OrbitChartData tf={tf} />}
    </Panel>
  )
}

function OrbitChartData({ tf }: { tf: Timeframe }) {
  const asset = useTerminal((s) => s.asset)
  const { components } = useComponents()
  const suggestions = useSuggestions(!!components?.strategy)
  return (
    <Suspense fallback={<QueryState isPending error={null} what="chart" />}>
      <OrbitChart asset={asset} tf={tf} pending={suggestions.data?.find((s) => s.suggestion.asset === asset)} />
    </Suspense>
  )
}
