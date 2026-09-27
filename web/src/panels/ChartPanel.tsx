import { useAstro, useCandles, useSignals, useSuggestions } from '../api/hooks'
import { Seg } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSETS, ASSET_META, TV_INTERVALS } from '../config'
import { useTerminal, type ChartMode } from '../state/store'
import { OrbitChart } from './chart/OrbitChart'
import { TradingViewChart } from './chart/TradingViewChart'

const MODES: { label: string; value: ChartMode }[] = [
  { label: 'LIVE', value: 'LIVE' },
  { label: 'ORBIT', value: 'ORBIT' },
]

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
      title={`${meta.name} · ${mode === 'LIVE' ? 'TradingView live' : 'Orbit daily'}`}
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

function OrbitChartData() {
  const asset = useTerminal((s) => s.asset)
  const candles = useCandles(asset)
  const signals = useSignals(asset)
  const astro = useAstro()
  const suggestions = useSuggestions()
  if (candles.isError) return <p className="load-err">Couldn't load candles: {String(candles.error)}</p>
  return (
    <OrbitChart
      asset={asset}
      candles={candles.data ?? []}
      signals={signals.data ?? []}
      transits={astro.data ?? []}
      pending={suggestions.data?.find((s) => s.suggestion.asset === asset)}
    />
  )
}
