import { ColorType, createChart, LineSeries, LineStyle, type UTCTimestamp } from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import { useDrift } from '../api/hooks'
import type { DriftReport } from '../api/types'
import { Pill } from '../components/bits'
import { Panel } from '../components/Panel'
import { num, signed } from '../lib/format'
import { readTheme } from '../lib/theme'

const ts = (iso: string) => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp
const pct = (v: number) => `${num(v * 100, 0)}%`

function EquityChart({ report }: { report: DriftReport }) {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = host.current
    if (!el) return
    const th = readTheme()
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: th.panel }, textColor: th.text2, fontFamily: th.mono, fontSize: 11 },
      grid: { vertLines: { color: th.line }, horzLines: { color: th.line } },
      rightPriceScale: { borderColor: th.line2 },
      timeScale: { borderColor: th.line2 },
      handleScroll: false,
      handleScale: false,
    })
    const quiet = { lineWidth: 1 as const, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }
    const band = (sign: 1 | -1) => report.curve.map((p) => ({ time: ts(p.time), value: p.expected + sign * p.band }))
    chart.addSeries(LineSeries, { ...quiet, color: th.line2, lineStyle: LineStyle.Dotted }).setData(band(1))
    chart.addSeries(LineSeries, { ...quiet, color: th.line2, lineStyle: LineStyle.Dotted }).setData(band(-1))
    chart
      .addSeries(LineSeries, { lineWidth: 1, color: th.text2, lineStyle: LineStyle.Dashed, priceLineVisible: false, title: 'BACKTEST' })
      .setData(report.curve.map((p) => ({ time: ts(p.time), value: p.expected })))
    chart
      .addSeries(LineSeries, { lineWidth: 2, color: th.accent, priceLineVisible: false, title: 'LIVE' })
      .setData(report.curve.map((p) => ({ time: ts(p.time), value: p.live })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [report])
  return <div className="lw-host" ref={host} />
}

export function DriftPanel({ hidden }: { hidden: boolean }) {
  const { data: d, isError, error } = useDrift()
  const tonePill = d?.status === 'OK' ? 'ok' : d?.status === 'WATCH' ? 'watch' : 'drift'
  return (
    <Panel
      code="DRIFT"
      title="Backtest vs live"
      hidden={hidden}
      meta={
        d && (
          <>
            <Pill tone={tonePill}>{d.status}</Pill>
            <span>z {signed(d.z_score)}σ</span>
          </>
        )
      }
    >
      {isError && <p className="load-err">Couldn't load drift: {String(error)}</p>}
      {d && (
        <div className="drift">
          <div className="dstats">
            <table>
              <thead>
                <tr>
                  <th />
                  <th>BACKTEST</th>
                  <th>LIVE</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Win rate</td>
                  <td>{pct(d.expected_win_rate)}</td>
                  <td className={d.live_win_rate < d.expected_win_rate ? 'down' : 'up'}>{pct(d.live_win_rate)}</td>
                </tr>
                <tr>
                  <td>Avg R</td>
                  <td>{num(d.expected_avg_r)}</td>
                  <td className={d.live_avg_r < d.expected_avg_r ? 'down' : 'up'}>{num(d.live_avg_r)}</td>
                </tr>
                <tr>
                  <td>Max DD</td>
                  <td>{num(d.expected_max_dd, 1)}%</td>
                  <td className={d.live_max_dd < d.expected_max_dd ? 'down' : 'up'}>{num(d.live_max_dd, 1)}%</td>
                </tr>
                <tr>
                  <td>Trades</td>
                  <td className="mid">{d.backtest_trades}</td>
                  <td>{d.live_trades}</td>
                </tr>
              </tbody>
            </table>
            <div>
              <span className="lbl">Win-rate drift, z-score</span>
              <div className="zgauge" role="img" aria-label={`z-score ${d.z_score.toFixed(2)}`}>
                <div className="rail" />
                <div className="pin" style={{ left: `calc(${Math.max(0, Math.min(100, ((d.z_score + 3) / 6) * 100))}% - 1px)` }} />
                <div className="ticks">
                  {['−3', '−2', '−1', '0', '+1', '+2', '+3'].map((t) => (
                    <span key={t}>{t}</span>
                  ))}
                </div>
              </div>
            </div>
            <p className="dnote">
              Live win rate is <b className="hi">{num(Math.abs(d.z_score), 1)}σ</b> {d.z_score < 0 ? 'below' : 'above'} the backtest across {d.live_trades} trades.{' '}
              {Math.abs(d.z_score) < d.scale_down_at ? 'Sizing is unchanged for now.' : 'Orbit has scaled itself down.'} Orbit scales down at {num(d.scale_down_at, 1)}σ.
            </p>
          </div>
          <div className="dchart">
            <div className="chart-wrap">
              <div className="overlay">
                <div className="chart-keys">
                  <span>
                    <b style={{ background: 'var(--text-2)' }} />
                    BACKTEST EXPECTED ±1σ
                  </span>
                  <span>
                    <b style={{ background: 'var(--accent)' }} />
                    LIVE EQUITY
                  </span>
                  <span>INDEXED TO 100 · {d.curve.length} DAYS</span>
                </div>
              </div>
              <EquityChart report={d} />
            </div>
          </div>
        </div>
      )}
    </Panel>
  )
}
