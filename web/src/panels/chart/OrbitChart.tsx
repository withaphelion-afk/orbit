import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Asset, AstroEvent, Candle, Signal, SuggestionView } from '../../api/types'
import { ASSET_META } from '../../config'
import { price, signed, tone } from '../../lib/format'
import { sma } from '../../lib/indicators'
import { readTheme } from '../../lib/theme'
import { useTerminal } from '../../state/store'

const ts = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp

interface Props {
  asset: Asset
  candles: Candle[]
  signals: Signal[]
  transits: AstroEvent[]
  pending?: SuggestionView
}

interface Series {
  chart: IChartApi
  candles: ISeriesApi<'Candlestick'>
  volume: ISeriesApi<'Histogram'>
  s20: ISeriesApi<'Line'>
  s50: ISeriesApi<'Line'>
  markers: ISeriesMarkersPluginApi<Time>
}

/**
 * Orbit's own chart (TradingView lightweight-charts): candles, volume, 20/50D
 * averages, signal and transit markers, and the pending suggestion's
 * entry/stop/target lines. The last bar follows live ticks.
 */
export function OrbitChart({ asset, candles, signals, transits, pending }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const api = useRef<Series | null>(null)
  const lines = useRef<IPriceLine[]>([])
  const lastBar = useRef<CandlestickData<UTCTimestamp> | null>(null)
  const [hover, setHover] = useState<CandlestickData<Time> | null>(null)
  const livePrice = useTerminal((s) => s.prices[asset])
  const dp = ASSET_META[asset].dp

  // Create the chart once.
  useEffect(() => {
    const el = host.current
    if (!el) return
    const th = readTheme()
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: th.panel }, textColor: th.text2, fontFamily: th.mono, fontSize: 11 },
      grid: { vertLines: { color: th.line }, horzLines: { color: th.line } },
      rightPriceScale: { borderColor: th.line2, scaleMargins: { top: 0.12, bottom: 0.2 } },
      timeScale: { borderColor: th.line2, rightOffset: 4, barSpacing: 7 },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: th.text3, labelBackgroundColor: th.text2 },
        horzLine: { color: th.text3, labelBackgroundColor: th.text2 },
      },
    })
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: th.up,
      downColor: th.down,
      wickUpColor: th.up,
      wickDownColor: th.down,
      borderVisible: false,
    })
    const volume = chart.addSeries(HistogramSeries, { priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } })
    const lineOpts = { lineWidth: 1 as const, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }
    const s20 = chart.addSeries(LineSeries, { ...lineOpts, color: th.text2 })
    const s50 = chart.addSeries(LineSeries, { ...lineOpts, color: th.accentLo })
    const markers = createSeriesMarkers(candleSeries, [])
    chart.subscribeCrosshairMove((p) => {
      const d = p.seriesData.get(candleSeries) as CandlestickData<Time> | undefined
      setHover(d ?? null)
    })
    api.current = { chart, candles: candleSeries, volume, s20, s50, markers }
    return () => {
      chart.remove()
      api.current = null
      lines.current = []
    }
  }, [])

  // Data.
  useEffect(() => {
    const a = api.current
    if (!a || !candles.length) return
    const th = readTheme()
    const bars = candles.map((c) => ({ time: ts(c.timestamp), open: c.open, high: c.high, low: c.low, close: c.close }))
    a.candles.setData(bars)
    a.candles.applyOptions({ priceFormat: { type: 'price', precision: dp, minMove: 1 / 10 ** dp } })
    a.volume.setData(candles.map((c) => ({ time: ts(c.timestamp), value: c.volume, color: (c.close >= c.open ? th.up : th.down) + '47' })))
    const closes = candles.map((c) => c.close)
    const toLine = (vals: number[]) => vals.flatMap((v, i) => (Number.isNaN(v) ? [] : [{ time: bars[i].time, value: v }]))
    a.s20.setData(toLine(sma(closes, 20)))
    a.s50.setData(toLine(sma(closes, 50)))
    lastBar.current = { ...bars[bars.length - 1] }
    a.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 130), to: bars.length + 3 })
  }, [candles, dp])

  // Markers: signals below/above bars, transits as violet squares on their day.
  useEffect(() => {
    const a = api.current
    if (!a || !candles.length) return
    const th = readTheme()
    const first = ts(candles[0].timestamp)
    const last = ts(candles[candles.length - 1].timestamp)
    const m: SeriesMarker<Time>[] = signals.map((s) => ({
      time: ts(s.timestamp),
      position: s.direction === 'LONG' ? 'belowBar' : 'aboveBar',
      shape: s.direction === 'LONG' ? 'arrowUp' : 'arrowDown',
      color: s.direction === 'LONG' ? th.up : th.down,
      text: s.name === 'ma_cross' ? 'MA×' : s.name === 'rsi_extreme' ? (s.direction === 'LONG' ? 'RSI<30' : 'RSI>70') : s.name,
      size: 0.8,
    }))
    for (const e of transits) {
      const t = ts(e.timestamp)
      if (t < first || t > last) continue
      m.push({ time: t, position: 'aboveBar', shape: 'square', color: th.astro, text: `${e.body.slice(0, 3)} ${e.event.split(' ')[0].toUpperCase()}`, size: 0.6 })
    }
    m.sort((x, y) => (x.time as number) - (y.time as number))
    a.markers.setMarkers(m)
  }, [signals, transits, candles])

  // Pending suggestion levels.
  useEffect(() => {
    const a = api.current
    if (!a) return
    lines.current.forEach((l) => a.candles.removePriceLine(l))
    lines.current = []
    if (!pending) return
    const th = readTheme()
    const s = pending.suggestion
    const add = (title: string, p: number, color: string) =>
      lines.current.push(a.candles.createPriceLine({ price: p, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title }))
    add('TARGET', s.take_profit, th.up)
    add('ENTRY', s.entry_price, th.accent)
    add('STOP', s.stop_loss, th.down)
  }, [pending, candles])

  // Live ticks move the last bar.
  useEffect(() => {
    const a = api.current
    const b = lastBar.current
    if (!a || !b || livePrice === undefined) return
    b.close = livePrice
    b.high = Math.max(b.high, livePrice)
    b.low = Math.min(b.low, livePrice)
    a.candles.update({ ...b })
  }, [livePrice])

  // Legend shows the hovered bar, or the live last bar when the pointer is off the chart.
  const legend = useMemo(() => {
    if (!candles.length) return null
    let i = candles.length - 1
    let bar = { open: candles[i].open, high: candles[i].high, low: candles[i].low, close: candles[i].close }
    if (hover) {
      const k = candles.findIndex((c) => ts(c.timestamp) === hover.time)
      if (k >= 0) {
        i = k
        bar = { open: hover.open, high: hover.high, low: hover.low, close: hover.close }
      }
    }
    if (i === candles.length - 1 && livePrice !== undefined) {
      bar = { ...bar, close: livePrice, high: Math.max(bar.high, livePrice), low: Math.min(bar.low, livePrice) }
    }
    const prev = i > 0 ? candles[i - 1].close : undefined
    return { ...bar, ch: prev ? (bar.close / prev - 1) * 100 : 0 }
  }, [hover, candles, livePrice])

  return (
    <div className="chart-wrap">
      <div className="overlay">
        {legend && (
          <div className="legend">
            <span className="pair">{ASSET_META[asset].pair}</span>
            {(['open', 'high', 'low', 'close'] as const).map((k) => (
              <span key={k}>
                <i>{k[0].toUpperCase()}</i>
                {price(asset, legend[k])}
              </span>
            ))}
            <span className={tone(legend.ch)}>{signed(legend.ch)}%</span>
          </div>
        )}
        <div className="chart-keys">
          <span>
            <b style={{ background: 'var(--up)' }} />
            SIGNAL
          </span>
          <span>
            <b style={{ background: 'var(--astro)' }} />
            TRANSIT
          </span>
          <span>
            <b style={{ background: 'var(--text-2)' }} />
            20D
          </span>
          <span>
            <b style={{ background: 'var(--accent-lo)' }} />
            50D
          </span>
          {pending && (
            <span>
              <b style={{ background: 'var(--accent)' }} />
              PENDING {pending.suggestion.direction} · CONF {pending.suggestion.confidence.toFixed(2)}
            </span>
          )}
        </div>
      </div>
      <div className="lw-host" ref={host} />
    </div>
  )
}
