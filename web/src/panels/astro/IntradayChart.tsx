import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import { useIntraday } from '../../api/hooks'
import type { Asset, PatternOccurrence } from '../../api/types'
import { QueryState } from '../../components/bits'
import { ASSET_META } from '../../config'
import { day, hhmm, signed, transitLabel } from '../../lib/format'
import { readTheme } from '../../lib/theme'

const BEFORE_HOURS = 72
const ts = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp
const hourOf = (iso: string) => (Math.floor(Date.parse(iso) / 3_600_000) * 3600) as UTCTimestamp

/** Hourly candles around one occurrence: 72h before the exact moment to the end
 * of its window, with the exact moment, the "move began" hour and the peak marked. */
export function IntradayChart({ asset, occ, windowDays }: { asset: Asset; occ: PatternOccurrence; windowDays: number }) {
  const moment = occ.event.exact_time ?? occ.date
  const afterHours = 24 * Math.min(windowDays, 20)
  const { data, isPending, error } = useIntraday(asset, moment, BEFORE_HOURS, afterHours)
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = host.current
    if (!el || !data?.length) return
    const th = readTheme()
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: th.panel }, textColor: th.text2, fontFamily: th.mono, fontSize: 11 },
      grid: { vertLines: { color: th.line }, horzLines: { color: th.line } },
      rightPriceScale: { borderColor: th.line2 },
      timeScale: { borderColor: th.line2, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    })
    const series = chart.addSeries(CandlestickSeries, { upColor: th.up, downColor: th.down, wickUpColor: th.up, wickDownColor: th.down, borderVisible: false })
    const dp = ASSET_META[asset].dp
    series.applyOptions({ priceFormat: { type: 'price', precision: dp, minMove: 1 / 10 ** dp } })
    series.setData(data.map((c) => ({ time: ts(c.timestamp), open: c.open, high: c.high, low: c.low, close: c.close })))

    const times = data.map((c) => ts(c.timestamp))
    const at = (t: number) => times.find((x) => x >= t) ?? times[times.length - 1]
    const exact = at(hourOf(moment))
    const markers: SeriesMarker<Time>[] = [{ time: exact, position: 'aboveBar', shape: 'arrowDown', color: th.astro, text: `EXACT ${hhmm(moment)}`, size: 1 }]
    const up = occ.peak_return !== null ? occ.peak_return >= 0 : true
    if (occ.hours_to_move !== null) {
      markers.push({ time: at(exact + occ.hours_to_move * 3600), position: up ? 'belowBar' : 'aboveBar', shape: 'circle', color: th.accent, text: `MOVE +${occ.hours_to_move}h`, size: 0.8 })
    }
    if (occ.hours_to_peak !== null && occ.peak_return !== null) {
      markers.push({ time: at(exact + occ.hours_to_peak * 3600), position: up ? 'aboveBar' : 'belowBar', shape: up ? 'arrowDown' : 'arrowUp', color: up ? th.up : th.down, text: `PEAK ${signed(occ.peak_return * 100, 1)}%`, size: 0.8 })
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number))
    createSeriesMarkers(series, markers)
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [data, asset, moment, occ])

  return (
    <div className="intraday">
      <div className="intraday-head">
        <span className="lbl">
          Hourly · {transitLabel(occ.event)} · exact {day(moment)} {new Date(moment).getUTCFullYear()} {hhmm(moment)}
        </span>
        <span className="dim">72h before → {Math.min(windowDays, 20)}d after</span>
      </div>
      {!data?.length ? (
        <QueryState isPending={isPending} error={error ?? (data ? new Error('No hourly bars in this window.') : null)} what="hourly bars" />
      ) : (
        <div className="intraday-chart" ref={host} />
      )}
    </div>
  )
}
