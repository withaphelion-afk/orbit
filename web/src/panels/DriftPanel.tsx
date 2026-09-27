import { ColorType, createChart, LineSeries, LineStyle, type UTCTimestamp } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import { useBacktest, useCalibration, useComponents, useDrift } from '../api/hooks'
import type { BacktestReport, BacktestStats, CalibrationReport, DriftReport } from '../api/types'
import { Empty, NotBuilt, Pill, QueryState, Seg } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, num, signed, tone } from '../lib/format'
import { readTheme } from '../lib/theme'

const ts = (iso: string) => Math.floor(Date.parse(iso.length === 10 ? `${iso}T00:00:00Z` : iso) / 1000) as UTCTimestamp
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${num(v * 100, 0)}%`)
const r = (v: number | null | undefined, dp = 2) => (v === null || v === undefined ? '—' : `${signed(v, dp)}R`)

type View = 'DRIFT' | 'BACKTEST' | 'FEEDBACK'
const VIEWS: View[] = ['DRIFT', 'BACKTEST', 'FEEDBACK']

/** One or more lines on a lightweight chart; `dashed` lines are reference lines. */
function Lines({ lines }: { lines: { points: { time: UTCTimestamp; value: number }[]; color: string; title?: string; dashed?: boolean; dotted?: boolean; width?: 1 | 2 }[] }) {
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
    for (const l of lines) {
      chart
        .addSeries(LineSeries, {
          lineWidth: l.width ?? 1,
          color: l.color === 'accent' ? th.accent : l.color === 'muted' ? th.text2 : l.color === 'line' ? th.line2 : l.color,
          lineStyle: l.dotted ? LineStyle.Dotted : l.dashed ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: !!l.title,
          crosshairMarkerVisible: !!l.title,
          title: l.title,
        })
        .setData(l.points)
    }
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [lines])
  return <div className="lw-host" ref={host} />
}

export function DriftPanel({ hidden }: { hidden: boolean }) {
  const [view, setView] = useState<View>('DRIFT')
  const { components, error: sysError, isPending: sysPending } = useComponents()
  const built = !!components?.backtest
  const drift = useDrift(built)
  const d = drift.data
  const tonePill = d?.status === 'OK' ? 'ok' : d?.status === 'WATCH' ? 'watch' : 'drift'
  return (
    <Panel
      code="DRIFT"
      title={view === 'DRIFT' ? 'Backtest vs live' : view === 'BACKTEST' ? 'RSI divergence backtest, full history' : 'Feedback loop: how confidence is set'}
      hidden={hidden}
      meta={
        <>
          {view === 'DRIFT' && d && (
            <>
              <Pill tone={tonePill}>{d.live_trades < d.min_trades ? 'WAITING' : d.status}</Pill>
              <span>z {signed(d.z_score)}σ</span>
            </>
          )}
          <Seg label="View" value={view} onChange={setView} options={VIEWS.map((v) => ({ label: v, value: v }))} />
        </>
      }
    >
      {!components ? (
        <QueryState isPending={sysPending} error={sysError} what="system status" />
      ) : !built ? (
        <NotBuilt layer="BACKTEST">
          <span>No backtest has been run yet. Press RUN ANALYSIS on SYS (F8): every run backtests the strategy on the full history.</span>
        </NotBuilt>
      ) : view === 'DRIFT' ? (
        d ? <DriftView d={d} /> : <QueryState isPending={drift.isPending} error={drift.error} what="drift" />
      ) : view === 'BACKTEST' ? (
        <BacktestView />
      ) : (
        <FeedbackView />
      )}
    </Panel>
  )
}

function DriftView({ d }: { d: DriftReport }) {
  const waiting = d.live_trades < d.min_trades
  return (
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
              <td className={!d.live_trades ? 'dim' : d.live_win_rate < d.expected_win_rate ? 'down' : 'up'}>{d.live_trades ? pct(d.live_win_rate) : '—'}</td>
            </tr>
            <tr>
              <td>Avg R</td>
              <td>{r(d.expected_avg_r)}</td>
              <td className={!d.live_trades ? 'dim' : d.live_avg_r < d.expected_avg_r ? 'down' : 'up'}>{d.live_trades ? r(d.live_avg_r) : '—'}</td>
            </tr>
            <tr>
              <td>Max DD</td>
              <td>{r(d.expected_max_dd, 1)}</td>
              <td className={!d.live_trades ? 'dim' : d.live_max_dd < d.expected_max_dd ? 'down' : 'up'}>{d.live_trades ? r(d.live_max_dd, 1) : '—'}</td>
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
          {waiting ? (
            <>
              {d.live_trades} of the {d.min_trades} finished live suggestions needed before drift is judged. Every suggestion counts, taken or not,
              followed with the strategy's own levels.
            </>
          ) : (
            <>
              Live win rate is <b className="hi">{num(Math.abs(d.z_score), 1)}σ</b> {d.z_score < 0 ? 'below' : 'above'} the backtest across{' '}
              {d.live_trades} trades. {Math.abs(d.z_score) < d.scale_down_at ? 'Within the expected range.' : 'Beyond the scale-down line: reduce size.'} The
              line is {num(d.scale_down_at, 1)}σ.
            </>
          )}
        </p>
      </div>
      <div className="dchart">
        {d.curve.length ? (
          <div className="chart-wrap">
            <div className="overlay">
              <div className="chart-keys">
                <span>
                  <b style={{ background: 'var(--text-2)' }} />
                  BACKTEST EXPECTED ±1σ
                </span>
                <span>
                  <b style={{ background: 'var(--accent)' }} />
                  LIVE, CUMULATIVE R
                </span>
                <span>{d.live_trades} TRADES</span>
              </div>
            </div>
            <DriftChart d={d} />
          </div>
        ) : (
          <Empty title="NO LIVE OUTCOMES YET">
            <span>The curve starts when the first live suggestion reaches its target, stop or 30-bar limit.</span>
          </Empty>
        )}
      </div>
    </div>
  )
}

function DriftChart({ d }: { d: DriftReport }) {
  const [lines] = useState(() => {
    const at = (f: (p: DriftReport['curve'][number]) => number) => d.curve.map((p) => ({ time: ts(p.time), value: f(p) }))
    return [
      { points: at((p) => p.expected + p.band), color: 'line', dotted: true },
      { points: at((p) => p.expected - p.band), color: 'line', dotted: true },
      { points: at((p) => p.expected), color: 'muted', dashed: true, title: 'BACKTEST' },
      { points: at((p) => p.live), color: 'accent', title: 'LIVE', width: 2 as const },
    ]
  })
  return <Lines lines={lines} />
}

function StatsRow({ label, s }: { label: string; s: BacktestStats }) {
  return (
    <tr>
      <td className="l strong">{label}</td>
      <td>{s.trades}</td>
      <td>{pct(s.win_rate)}</td>
      <td className={tone(s.avg_r)}>{r(s.avg_r, 3)}</td>
      <td className={tone(s.total_r)}>{r(s.total_r, 1)}</td>
      <td>{s.profit_factor === null ? '—' : num(s.profit_factor, 2)}</td>
      <td className="down">{r(s.max_drawdown_r, 1)}</td>
      <td className={tone(s.by_direction.LONG.avg_r ?? 0)}>
        {s.by_direction.LONG.trades} · {r(s.by_direction.LONG.avg_r)}
      </td>
      <td className={tone(s.by_direction.SHORT.avg_r ?? 0)}>
        {s.by_direction.SHORT.trades} · {r(s.by_direction.SHORT.avg_r)}
      </td>
      <td className="mid">
        {s.exit_reasons.target}/{s.exit_reasons.stop}/{s.exit_reasons.time}
      </td>
    </tr>
  )
}

function BacktestView() {
  const { data, isPending, error } = useBacktest(true)
  if (!data) return <QueryState isPending={isPending} error={error} what="the backtest" />
  return <BacktestBody b={data} />
}

function BacktestBody({ b }: { b: BacktestReport }) {
  const p = b.pooled
  const [lines] = useState(() => [{ points: dedupe(p.equity_r ?? []), color: 'accent', title: 'POOLED R', width: 2 as const }])
  const years = Object.entries(p.by_year).sort()
  return (
    <div className="bt">
      <div className="pbk-tools">
        <span className="dim">
          {b.strategy} on daily bars, every asset's full stored history: entry at the next open, stop beyond the swing, target 2R, out after 30
          bars, one trade at a time, costs and slippage included. Parameters are textbook, not fitted. Run {day(b.generated_at)}.
        </span>
      </div>
      <div className="tbl-wrap bt-table">
        <table className="tbl">
          <thead>
            <tr>
              <th className="l">Asset</th>
              <th>Trades</th>
              <th>Win rate</th>
              <th title="Average result per trade, in units of the risk taken">Avg R</th>
              <th>Total R</th>
              <th title="Gross wins / gross losses">Profit factor</th>
              <th>Max DD</th>
              <th>Long · avg</th>
              <th>Short · avg</th>
              <th title="Exits at target / stop / time limit">T/S/Time</th>
            </tr>
          </thead>
          <tbody>
            <StatsRow label="ALL" s={p} />
            {Object.entries(b.assets).map(([a, s]) => (
              <StatsRow key={a} label={ASSET_META[a as keyof typeof ASSET_META]?.label ?? a} s={s} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="bt-bottom">
        <div className="dchart">
          <div className="chart-wrap">
            <div className="overlay">
              <div className="chart-keys">
                <span>
                  <b style={{ background: 'var(--accent)' }} />
                  CUMULATIVE R, ALL ASSETS
                </span>
              </div>
            </div>
            <Lines lines={lines} />
          </div>
        </div>
        <div className="tbl-wrap bt-years">
          <table className="tbl">
            <thead>
              <tr>
                <th className="l">Year</th>
                <th>Trades</th>
                <th>Win</th>
                <th>R</th>
              </tr>
            </thead>
            <tbody>
              {years.map(([y, v]) => (
                <tr key={y}>
                  <td className="l">{y}</td>
                  <td>{v.trades}</td>
                  <td>{pct(v.wins / v.trades)}</td>
                  <td className={tone(v.r)}>{r(v.r, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

/** One point per day (the chart needs unique times): keep each day's last value. */
function dedupe(points: { date: string; r: number }[]) {
  const byDay = new Map<string, number>()
  for (const q of points) byDay.set(q.date, q.r)
  return [...byDay].map(([date, value]) => ({ time: ts(date), value }))
}

const FEATURE: Record<string, string> = {
  rsi_difference: 'RSI divergence size',
  rsi_level: 'RSI level at the second swing',
  price_change_abs: 'Price move between swings',
  bars_between: 'Bars between swings',
  atr_pct: 'ATR as % of price',
  volatility_pct: 'Volatility percentile',
  trend_aligned: 'Trend agrees with the trade',
  is_long: 'Long (vs short)',
}

function FeedbackView() {
  const { data, isPending, error } = useCalibration(true)
  if (!data) return <QueryState isPending={isPending} error={error} what="the feedback loop" />
  return <FeedbackBody c={data} />
}

function FeedbackBody({ c }: { c: CalibrationReport }) {
  const o = c.out_of_sample
  const maxW = Math.max(...(c.weights ?? []).map((w) => Math.abs(w.weight)), 1e-9)
  return (
    <div className="fb">
      <div className="jbar">
        <div>
          <span className="lbl">Learned from</span>
          <span className="v">
            {c.n_backtest} backtest + {c.n_live} live
          </span>
        </div>
        <div>
          <span className="lbl">Plain win rate</span>
          <span className="v">{pct(c.base_win_rate)}</span>
        </div>
        <div title="Brier score on years the model hadn't seen (lower is better) vs always predicting the plain win rate">
          <span className="lbl">Out-of-sample Brier</span>
          <span className="v">{o ? `${num(o.brier, 4)} vs ${num(o.brier_base_rate, 4)}` : '—'}</span>
        </div>
        <div>
          <span className="lbl">AUC</span>
          <span className="v">{o?.auc == null ? '—' : num(o.auc, 2)}</span>
        </div>
        <div>
          <span className="lbl">Sets confidence?</span>
          <span className={`v ${c.skill ? 'up' : 'warn'}`}>{c.skill ? 'YES' : 'NOT YET'}</span>
        </div>
      </div>
      <p className="dnote fb-note">
        {c.skill
          ? 'The model beat the plain win rate on years it had not seen, so each suggestion’s confidence is its estimated chance of winning.'
          : `The model has not beaten the plain win rate on years it had not seen, so every suggestion gets the plain win rate (${pct(c.base_win_rate)}) as confidence. It retrains on every analysis run with each new live outcome counted 3×, and takes over if it starts to beat that.`}
        {c.note ? ` ${c.note}` : ''} Trained {day(c.trained_at)}.
      </p>
      <div className="fb-grid">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th className="l" title="Out-of-sample predictions, in fifths">Predicted</th>
                <th>Actually won</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {(o?.buckets ?? []).map((b) => (
                <tr key={b.predicted}>
                  <td className="l">{pct(b.predicted)}</td>
                  <td className={Math.abs(b.actual - b.predicted) < 0.08 ? 'up' : 'warn'}>{pct(b.actual)}</td>
                  <td className="mid">{b.n}</td>
                </tr>
              ))}
              {!o && (
                <tr>
                  <td colSpan={3} className="l dim empty-row">
                    Not enough history for an out-of-sample check yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th className="l">What the model looks at</th>
                <th className="l" title="Standardised weight: right = more likely to win">Effect on P(win)</th>
              </tr>
            </thead>
            <tbody>
              {(c.weights ?? []).map((w) => (
                <tr key={w.feature}>
                  <td className="l">{FEATURE[w.feature] ?? w.feature}</td>
                  <td className="l">
                    <span className="wbar">
                      <i className={w.weight > 0 ? 'pos' : 'neg'} style={{ width: `${(Math.abs(w.weight) / maxW) * 50}%` }} />
                    </span>
                    <span className={w.weight > 0 ? 'up' : 'down'}>{signed(w.weight, 2)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
