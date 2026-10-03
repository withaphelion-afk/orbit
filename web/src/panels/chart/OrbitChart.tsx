import {
  BaselineSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { ArrowDownRight, ArrowUpRight, Check, MousePointerClick, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useBars, useDivergenceModel, useDivergences, useLabelDivergence, useRegime } from '../../api/hooks'
import type { Asset, BarRow, DivergenceCandidate, SuggestionView, Timeframe } from '../../api/types'
import { Empty, Pill, QueryState } from '../../components/bits'
import { ASSET_META } from '../../config'
import { BINANCE_SYMBOL, fetchKlines, subscribeKlines } from '../../lib/binance'
import { find, rsi, type Candidate } from '../../lib/divergence'
import { context, features, score } from '../../lib/divergenceScore'
import { pct, price } from '../../lib/format'
import { readTheme } from '../../lib/theme'
import { useTerminal } from '../../state/store'

const MAX_LINES = 12
const TF_LABEL: Record<Timeframe, string> = { '1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W' }

interface Props {
  asset: Asset
  tf: Timeframe
  pending?: SuggestionView
}

/** A divergence as drawn: detected here (live) and/or published by the runner, with its score and your label. */
export interface Drawn {
  id: string
  c: Candidate
  t1: number
  t2: number
  forming: boolean
  score: number | null
  alert: boolean
  you: 'real' | 'not' | null
  outcome: 'worked' | 'failed' | null
}

/** Bars for the chart: Binance live for crypto (the forming bar included), Orbit's own bars for silver. */
function useChartBars(asset: Asset, tf: Timeframe): { bars: BarRow[] | null; live: boolean; error: unknown; closedTick: number } {
  const symbol = BINANCE_SYMBOL[asset]
  const stored = useBars(asset, tf, !symbol)
  const key = `${symbol}|${tf}`
  // Kept with the series they belong to, so a switch of asset or timeframe never shows the old bars.
  const [state, setState] = useState<{ key: string; rows: BarRow[] | null; error: unknown }>({ key, rows: null, error: null })
  const [closedTick, setClosedTick] = useState(0)
  useEffect(() => {
    if (!symbol) return
    let stop = () => {}
    let cancelled = false
    fetchKlines(symbol, tf)
      .then((initial) => {
        if (cancelled) return
        setState({ key, rows: initial, error: null })
        stop = subscribeKlines(symbol, tf, (bar, closed) => {
          setState((prev) => {
            if (prev.key !== key || !prev.rows) return prev
            const last = prev.rows[prev.rows.length - 1]
            if (last[0] === bar[0]) return { ...prev, rows: [...prev.rows.slice(0, -1), bar] }
            return bar[0] > last[0] ? { ...prev, rows: [...prev.rows.slice(-1999), bar] } : prev
          })
          if (closed) setClosedTick((n) => n + 1)
        })
      })
      .catch((e) => !cancelled && setState({ key, rows: null, error: e }))
    return () => {
      cancelled = true
      stop()
    }
  }, [symbol, tf, key])
  const rows = state.key === key ? state.rows : null
  const error = state.key === key ? state.error : null
  if (!symbol) return { bars: stored.data ?? null, live: false, error: stored.error, closedTick: 0 }
  return { bars: rows, live: true, error, closedTick }
}

/**
 * Orbit's live divergence chart (lightweight-charts): candles with an RSI(14) pane (70/30 bands, fills,
 * the 50 line), every divergence the shared algorithm finds drawn on price and RSI, solid once confirmed
 * and dashed while forming, with the learned model's score. Detection reruns on every tick; a divergence
 * that confirms with a score above its timeframe's threshold raises an alert right away.
 */
export function OrbitChart({ asset, tf, pending }: Props) {
  const { bars, live, error, closedTick } = useChartBars(asset, tf)
  const model = useDivergenceModel().data
  const published = useDivergences(asset).data
  const regimes = useRegime().data
  const label = useLabelDivergence()
  const notify = useTerminal((s) => s.notify)
  const addLiveAlert = useTerminal((s) => s.addLiveAlert)
  const [marking, setMarking] = useState<number[]>([]) // bar times clicked while marking a missed divergence
  const [markMode, setMarkMode] = useState(false)

  const regime = useMemo(() => {
    const r = regimes?.find((x) => (asset === 'SILVER' ? x.asset === 'SILVER' : x.scope === 'SHARED'))?.value
    return r === 'BULL' ? 1 : r === 'BEAR' ? -1 : 0
  }, [regimes, asset])

  // Detection + scoring, on every tick. A divergence confirmed on a bar that hasn't closed yet still counts as forming.
  const drawn = useMemo<Drawn[]>(() => {
    if (!bars || bars.length < 30) return []
    const high = bars.map((b) => b[2])
    const low = bars.map((b) => b[3])
    const close = bars.map((b) => b[4])
    const ctx = context(bars)
    const threshold = model?.thresholds?.[tf] ?? published?.thresholds?.[tf] ?? 1
    const known = new Map((published?.candidates?.[tf] ?? []).map((c) => [c.id, c]))
    const lastOpen = live ? bars.length - 1 : -1
    return find(high, low, close).map((c) => {
      const t1 = bars[c.i][0]
      const t2 = bars[c.j][0]
      const id = `${asset}|${tf}|${t1}|${t2}|${c.direction}`
      const pub: DivergenceCandidate | undefined = known.get(id)
      const forming = c.confirm === null || c.confirm === lastOpen
      const s = score(model, features(c, bars, ctx, asset, tf, regime)) ?? pub?.score ?? null
      return { id, c, t1, t2, forming, score: s, alert: !forming && s !== null && s >= threshold, you: pub?.you ?? null, outcome: pub?.outcome ?? null }
    })
  }, [bars, model, published, tf, asset, live, regime])

  // Alert the moment a divergence confirms on a closed bar with a score above the threshold.
  const alerted = useRef(new Set<string>())
  const primed = useRef(false)
  useEffect(() => {
    const fresh = drawn.filter((d) => d.alert && !alerted.current.has(d.id))
    fresh.forEach((d) => alerted.current.add(d.id))
    if (!primed.current) {
      primed.current = drawn.length > 0 // everything already on the chart when it loads isn't news
      return
    }
    for (const d of fresh) {
      addLiveAlert({ ...d.c, id: d.id, kind: d.c.kind, forming: false, t1: d.t1, t2: d.t2, confirmed_at: bars?.[d.c.confirm!]?.[0] ?? null, score: d.score,
        oos_score: null, alert: true, outcome: null, you: null, asset, timeframe: tf, trusted: !!model?.trusted })
      notify(`DIVERGENCE · ${ASSET_META[asset].label} ${TF_LABEL[tf]} ${d.c.direction} · score ${d.score === null ? '—' : pct(d.score)}`)
    }
  }, [closedTick, drawn, addLiveAlert, notify, asset, tf, model, bars])
  useEffect(() => {
    alerted.current = new Set()
    primed.current = false
  }, [asset, tf])

  // One divergence per swing on the chart and in the list: several earlier swings can pair with the same one,
  // and only the best-scoring (or the one you labelled) is worth a line.
  const shown = useMemo(() => {
    const best = new Map<string, Drawn>()
    for (const d of drawn.filter((x) => x.forming || x.alert || x.you)) {
      const key = `${d.c.j}|${d.c.direction}`
      const cur = best.get(key)
      if (!cur || (d.you && !cur.you) || (!cur.you && (d.score ?? 0) > (cur.score ?? 0))) best.set(key, d)
    }
    return [...best.values()].sort((a, b) => a.c.j - b.c.j)
  }, [drawn])

  const teach = (d: Drawn, verdict: 'real' | 'not') =>
    label.mutate(
      { asset, timeframe: tf, t1: d.t1, t2: d.t2, direction: d.c.direction, verdict },
      {
        onSuccess: () => notify(`LABELLED ${verdict === 'real' ? '✓ REAL' : '✗ NOT REAL'} · the model learns it on the next run`),
        onError: (e) => notify(`NOT SAVED: ${String(e)}`, true),
      },
    )

  const onPick = (t: number, isLow: boolean) => {
    const next = [...marking, t]
    if (next.length < 2) return setMarking(next)
    const [t1, t2] = next.sort((a, b) => a - b)
    setMarking([])
    setMarkMode(false)
    label.mutate(
      { asset, timeframe: tf, t1, t2, direction: isLow ? 'LONG' : 'SHORT', verdict: 'real', source: 'manual' },
      { onSuccess: () => notify('MARKED A MISSED DIVERGENCE · the model learns it on the next run'), onError: (e) => notify(`NOT SAVED: ${String(e)}`, true) },
    )
  }

  if (!bars) return <QueryState isPending={!error} error={error} what={`${TF_LABEL[tf]} bars`} />
  const threshold = model?.thresholds?.[tf]
  const list = shown.slice(-40).reverse()

  return (
    <div className="dv">
      <div className="dv-chart">
        <Canvas asset={asset} bars={bars} drawn={shown} pending={pending?.timeframe === tf ? pending : undefined} markMode={markMode} onPick={onPick} />
        <div className="dv-legend">
          <span>{live ? 'Live · Binance' : 'Orbit bars · hourly'}</span>
          <span>RSI(14) · 70/30</span>
          {model ? <Pill tone={model.trusted ? 'ok' : 'watch'}>{model.trusted ? 'MODEL TRUSTED' : 'MODEL UNPROVEN'}</Pill> : <span>Model not trained yet</span>}
          {threshold !== undefined && <span>Alerts at ≥ {pct(threshold)}</span>}
        </div>
      </div>
      <aside className="dv-list">
        <div className="dv-list-head">
          <span className="dv-title">Divergences · {TF_LABEL[tf]}</span>
          <button
            type="button"
            className={`act mod dv-mark ${markMode ? 'on' : ''}`}
            onClick={() => {
              setMarkMode(!markMode)
              setMarking([])
            }}
            title="Click the two swing points (lows for bullish, highs for bearish) of a divergence the detector missed"
          >
            <MousePointerClick size={14} strokeWidth={1.75} /> {markMode ? `Click swing ${marking.length + 1} of 2` : 'Mark missed'}
          </button>
        </div>
        {!list.length ? (
          <Empty title="NOTHING TO SHOW">
            <span>No confirmed divergence above the alert threshold, none forming, and none labelled in view.</span>
          </Empty>
        ) : (
          <div className="dv-rows">
            {list.map((d) => (
              <DivergenceRow key={d.id} asset={asset} d={d} trusted={!!model?.trusted} busy={label.isPending} onTeach={(v) => teach(d, v)} />
            ))}
          </div>
        )}
      </aside>
    </div>
  )
}

const when = (t: number) => new Date(t * 1000).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

/** One divergence in the list: direction, kind, score with its honesty label, the two swings, and ✓/✗. */
function DivergenceRow({ asset, d, trusted, busy, onTeach }: { asset: Asset; d: Drawn; trusted: boolean; busy: boolean; onTeach: (v: 'real' | 'not') => void }) {
  const up = d.c.direction === 'LONG'
  return (
    <div className={`dv-row ${up ? 'long' : 'short'} ${d.forming ? 'forming' : ''}`}>
      <div className="dv-top">
        <span className={`dv-dir ${up ? 'up' : 'down'}`}>
          {up ? <ArrowUpRight size={15} strokeWidth={2} aria-hidden="true" /> : <ArrowDownRight size={15} strokeWidth={2} aria-hidden="true" />}
          {up ? 'Bullish' : 'Bearish'}
        </span>
        <span className="dv-kind">{d.c.kind}</span>
        <span className="dv-score">{d.score === null ? '—' : pct(d.score)}</span>
      </div>
      <div className="dv-tags">
        {d.forming && <Pill tone="off">FORMING</Pill>}
        {!trusted && <Pill tone="watch" title="The model hasn't beaten the plain rate on data it hasn't seen yet">UNPROVEN</Pill>}
        {d.outcome && <em className={`pill dv-outcome ${d.outcome}`}>{d.outcome.toUpperCase()}</em>}
      </div>
      <dl className="dv-facts">
        <dt>Swings</dt>
        <dd>
          {when(d.t1)} → {when(d.t2)}
        </dd>
        <dt>Price</dt>
        <dd>
          {price(asset, d.c.p1)} → {price(asset, d.c.p2)}
        </dd>
        <dt>RSI</dt>
        <dd>
          {d.c.r1.toFixed(1)} → {d.c.r2.toFixed(1)}
        </dd>
      </dl>
      <div className="dv-teach">
        <button type="button" className={`act take ${d.you === 'real' ? 'on' : ''}`} onClick={() => onTeach('real')} disabled={busy} title="✓ A real divergence">
          <Check size={14} strokeWidth={2} /> Real
        </button>
        <button type="button" className={`act skip ${d.you === 'not' ? 'on' : ''}`} onClick={() => onTeach('not')} disabled={busy} title="✗ Not a real divergence">
          <X size={14} strokeWidth={2} /> Not real
        </button>
      </div>
    </div>
  )
}

interface CanvasProps {
  asset: Asset
  bars: BarRow[]
  drawn: Drawn[]
  pending?: SuggestionView
  markMode: boolean
  onPick: (t: number, isLow: boolean) => void
}

interface Api {
  chart: IChartApi
  candles: ISeriesApi<'Candlestick'>
  rsi: ISeriesApi<'Line'>
  hot: ISeriesApi<'Baseline'>
  cold: ISeriesApi<'Baseline'>
  markers: ISeriesMarkersPluginApi<Time>
}

function Canvas({ asset, bars, drawn, pending, markMode, onPick }: CanvasProps) {
  const host = useRef<HTMLDivElement>(null)
  const api = useRef<Api | null>(null)
  const lineSeries = useRef<ISeriesApi<'Line'>[]>([])
  const priceLines = useRef<IPriceLine[]>([])
  const pick = useRef({ markMode, onPick, bars })
  pick.current = { markMode, onPick, bars }
  const dp = ASSET_META[asset].dp

  useEffect(() => {
    const el = host.current
    if (!el) return
    const th = readTheme()
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: th.panel }, textColor: th.text2, fontFamily: th.mono, fontSize: 11, panes: { separatorColor: th.line2 } },
      grid: { vertLines: { color: th.line }, horzLines: { color: th.line } },
      rightPriceScale: { borderColor: th.line2 },
      timeScale: { borderColor: th.line2, rightOffset: 6, barSpacing: 7, timeVisible: true },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: th.text3, labelBackgroundColor: th.text2 }, horzLine: { color: th.text3, labelBackgroundColor: th.text2 } },
    })
    const candles = chart.addSeries(CandlestickSeries, { upColor: th.up, downColor: th.down, wickUpColor: th.up, wickDownColor: th.down, borderVisible: false })
    const quiet = { lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }
    // RSI pane: fills above 70 (red, overbought) and below 30 (green, oversold), then the line and its bands on top.
    const hot = chart.addSeries(BaselineSeries, { ...quiet, baseValue: { type: 'price', price: 70 }, topFillColor1: th.down + '55', topFillColor2: th.down + '22',
      topLineColor: 'transparent', bottomFillColor1: 'transparent', bottomFillColor2: 'transparent', bottomLineColor: 'transparent' }, 1)
    const cold = chart.addSeries(BaselineSeries, { ...quiet, baseValue: { type: 'price', price: 30 }, bottomFillColor1: th.up + '22', bottomFillColor2: th.up + '55',
      bottomLineColor: 'transparent', topFillColor1: 'transparent', topFillColor2: 'transparent', topLineColor: 'transparent' }, 1)
    const rsiLine = chart.addSeries(LineSeries, { color: th.accent, lineWidth: 1, priceLineVisible: false, lastValueVisible: true, autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) }, 1)
    for (const [v, style] of [[70, LineStyle.Dashed], [30, LineStyle.Dashed], [50, LineStyle.Dotted]] as const) {
      rsiLine.createPriceLine({ price: v, color: th.text3, lineWidth: 1, lineStyle: style, axisLabelVisible: false, title: '' })
    }
    chart.panes()[1]?.setHeight(150)
    const markers = createSeriesMarkers(candles, [])
    const onClick = (p: MouseEventParams<Time>) => {
      const { markMode: on, onPick: cb, bars: rows } = pick.current
      if (!on || p.time === undefined || !p.point) return
      const t = Number(p.time)
      const bar = rows.find((b) => b[0] === t)
      const y = candles.coordinateToPrice(p.point.y)
      if (!bar || y === null) return
      cb(t, y < (bar[2] + bar[3]) / 2)
    }
    chart.subscribeClick(onClick)
    api.current = { chart, candles, rsi: rsiLine, hot, cold, markers }
    return () => {
      chart.unsubscribeClick(onClick)
      chart.remove()
      api.current = null
      lineSeries.current = []
      priceLines.current = []
    }
  }, [])

  // Bars and RSI.
  const first = bars[0]?.[0]
  useEffect(() => {
    const a = api.current
    if (!a || !bars.length) return
    a.candles.applyOptions({ priceFormat: { type: 'price', precision: dp, minMove: 1 / 10 ** dp } })
    a.candles.setData(bars.map((b) => ({ time: b[0] as UTCTimestamp, open: b[1], high: b[2], low: b[3], close: b[4] })))
    const r = rsi(bars.map((b) => b[4]))
    const pts = bars.flatMap((b, k) => (Number.isNaN(r[k]) ? [] : [{ time: b[0] as UTCTimestamp, value: r[k] }]))
    a.rsi.setData(pts)
    a.hot.setData(pts)
    a.cold.setData(pts)
  }, [bars, dp])

  // Fit the view when the series itself changes (asset or timeframe), not on every tick.
  useEffect(() => {
    api.current?.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 160), to: bars.length + 4 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [first, asset])

  // Divergence lines on price and RSI, and score markers.
  useEffect(() => {
    const a = api.current
    if (!a) return
    const th = readTheme()
    lineSeries.current.forEach((s) => a.chart.removeSeries(s))
    lineSeries.current = []
    const show = drawn.slice(-MAX_LINES)
    const markers: SeriesMarker<Time>[] = []
    for (const d of show) {
      const color = d.c.direction === 'LONG' ? th.up : th.down
      const style = d.forming ? LineStyle.Dashed : LineStyle.Solid
      const opts = { color, lineWidth: 2 as const, lineStyle: style, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }
      const onPrice = a.chart.addSeries(LineSeries, opts, 0)
      onPrice.setData([{ time: d.t1 as UTCTimestamp, value: d.c.p1 }, { time: d.t2 as UTCTimestamp, value: d.c.p2 }])
      const onRsi = a.chart.addSeries(LineSeries, opts, 1)
      onRsi.setData([{ time: d.t1 as UTCTimestamp, value: d.c.r1 }, { time: d.t2 as UTCTimestamp, value: d.c.r2 }])
      lineSeries.current.push(onPrice, onRsi)
      markers.push({
        time: d.t2 as UTCTimestamp,
        position: d.c.direction === 'LONG' ? 'belowBar' : 'aboveBar',
        shape: d.c.direction === 'LONG' ? 'arrowUp' : 'arrowDown',
        color,
        text: `${d.forming ? 'forming' : d.score === null ? '' : pct(d.score)}${d.you === 'real' ? ' ✓' : ''}`,
        size: 0.8,
      })
    }
    markers.sort((x, y) => Number(x.time) - Number(y.time))
    a.markers.setMarkers(markers)
  }, [drawn])

  // A pending suggestion's levels on this timeframe.
  useEffect(() => {
    const a = api.current
    if (!a) return
    priceLines.current.forEach((l) => a.candles.removePriceLine(l))
    priceLines.current = []
    if (!pending) return
    const th = readTheme()
    const s = pending.suggestion
    const add = (title: string, p: number, color: string) =>
      priceLines.current.push(a.candles.createPriceLine({ price: p, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title }))
    add('TARGET', s.take_profit, th.up)
    add('ENTRY', s.entry_price, th.accent)
    add('STOP', s.stop_loss, th.down)
  }, [pending])

  return <div className={`lw-host ${markMode ? 'marking' : ''}`} ref={host} />
}
