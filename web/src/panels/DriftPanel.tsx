import { ColorType, createChart, LineSeries, LineStyle, type UTCTimestamp } from 'lightweight-charts'
import {
  Activity,
  ChartLine,
  Database,
  Gauge,
  Hash,
  Info,
  Percent,
  Radar,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sigma,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useBacktest, useCalibration, useComponents, useDrift } from '../api/hooks'
import type { BacktestReport, BacktestStats, CalibrationReport, DriftReport } from '../api/types'
import { Empty, NotBuilt, Pill, QueryState, Seg, StatCard, StatGrid } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, num, signed, tone } from '../lib/format'
import { readTheme } from '../lib/theme'

const ts = (iso: string) => Math.floor(Date.parse(iso.length === 10 ? `${iso}T00:00:00Z` : iso) / 1000) as UTCTimestamp
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${num(v * 100, 0)}%`)
const r = (v: number | null | undefined, dp = 2) => (v === null || v === undefined ? '—' : `${signed(v, dp)}R`)
const statTone = (v: number) => (v > 0 ? 'up' : v < 0 ? 'down' : undefined)
const ico = { size: 18, strokeWidth: 1.75 }

type View = 'DRIFT' | 'BACKTEST' | 'FEEDBACK'
const VIEWS: View[] = ['DRIFT', 'BACKTEST', 'FEEDBACK']

const TITLE: Record<View, string> = {
  DRIFT: 'Backtest vs live',
  BACKTEST: 'RSI divergence backtest, full history',
  FEEDBACK: 'Feedback loop: how confidence is set',
}

const DESCRIPTION: Record<View, string> = {
  DRIFT: 'Checks whether live suggestions win as often as the backtest said they would, and tells you when to scale down.',
  BACKTEST: "How the strategy would have traded every asset's full stored history, with costs and slippage included.",
  FEEDBACK: 'How each suggestion’s confidence is set, and whether the model behind it has earned the right to set it.',
}

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

/** A titled card inside a view; `aside` sits at the right of the card's header. */
function Card({ title, aside, className = '', children }: { title: string; aside?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`dr-card ${className}`}>
      <header className="dr-card-h">
        <h3>{title}</h3>
        {aside}
      </header>
      {children}
    </section>
  )
}

function Note({ children }: { children: ReactNode }) {
  return (
    <div className="dr-note">
      <Info size={16} strokeWidth={1.75} aria-hidden="true" />
      <p className="dnote">{children}</p>
    </div>
  )
}

export function DriftPanel({ hidden }: { hidden: boolean }) {
  const [view, setView] = useState<View>('DRIFT')
  const [tf, setTf] = useState<'1d' | '4h'>('1d')
  const { components, error: sysError, isPending: sysPending } = useComponents()
  const built = !!components?.backtest
  const drift = useDrift(built, tf)
  const d = drift.data
  const tonePill = d?.status === 'OK' ? 'ok' : d?.status === 'WATCH' ? 'watch' : 'drift'
  return (
    <Panel
      code="DRIFT"
      title={TITLE[view]}
      description={DESCRIPTION[view]}
      hidden={hidden}
      tools={
        <>
          <Seg label="View" value={view} onChange={setView} options={VIEWS.map((v) => ({ label: v, value: v }))} />
          {view !== 'FEEDBACK' && (
            <Seg
              label="Timeframe"
              value={tf}
              onChange={setTf}
              options={[
                { label: '1D', value: '1d' as const },
                { label: '4H', value: '4h' as const },
              ]}
            />
          )}
          {view === 'DRIFT' && d && (
            <div className="dr-status">
              <Pill
                tone={tonePill}
                title="OK, WATCH or DRIFT: how far the live win rate has moved from the backtest. WAITING until enough live suggestions have finished."
              >
                {d.live_trades < d.min_trades ? 'WAITING' : d.status}
              </Pill>
              <span className="dr-z" title="Win-rate drift: how far the live win rate sits from the backtest, in standard deviations">
                z {signed(d.z_score)}σ
              </span>
            </div>
          )}
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
        <BacktestView tf={tf} />
      ) : (
        <FeedbackView />
      )}
    </Panel>
  )
}

const Z_TICKS = ['−3', '−2', '−1', '0', '+1', '+2', '+3']

function DriftView({ d }: { d: DriftReport }) {
  const waiting = d.live_trades < d.min_trades
  const has = d.live_trades > 0
  const vs = (live: number, expected: number) => (!has ? 'dim' : live < expected ? 'down' : 'up')
  const status = waiting ? 'WAITING' : d.status
  return (
    <div className="dr-view dr-drift">
      <StatGrid>
        <StatCard
          label="Drift status"
          value={status}
          tone={waiting ? 'dim' : d.status === 'OK' ? 'up' : d.status === 'WATCH' ? 'warn' : 'down'}
          caption={
            waiting
              ? `${d.live_trades} of ${d.min_trades} live trades needed`
              : d.status === 'OK'
                ? 'Within the expected range'
                : d.status === 'WATCH'
                  ? 'Drifting, not yet at the scale-down line'
                  : 'Beyond the scale-down line: reduce size'
          }
          icon={<Activity {...ico} />}
        />
        <StatCard
          label="Z-score"
          value={`${signed(d.z_score)}σ`}
          tone={waiting ? 'dim' : d.status === 'DRIFT' ? 'down' : d.status === 'WATCH' ? 'warn' : undefined}
          caption={`Scale down at ±${num(d.scale_down_at, 1)}σ`}
          icon={<Sigma {...ico} />}
          title="How far the live win rate sits from the backtest's, in standard deviations"
        />
        <StatCard
          label="Live win rate"
          value={has ? pct(d.live_win_rate) : '—'}
          tone={vs(d.live_win_rate, d.expected_win_rate)}
          caption={`Backtest ${pct(d.expected_win_rate)}`}
          icon={<Target {...ico} />}
        />
        <StatCard
          label="Live avg R"
          value={has ? r(d.live_avg_r) : '—'}
          tone={vs(d.live_avg_r, d.expected_avg_r)}
          caption={`Backtest ${r(d.expected_avg_r)}`}
          icon={<TrendingUp {...ico} />}
          title="Average result per trade, in units of the risk taken"
        />
        <StatCard
          label="Live max DD"
          value={has ? r(d.live_max_dd, 1) : '—'}
          tone={vs(d.live_max_dd, d.expected_max_dd)}
          caption={`Backtest ${r(d.expected_max_dd, 1)}`}
          icon={<TrendingDown {...ico} />}
          title="Maximum drawdown: the deepest fall from a peak, in R"
        />
        <StatCard label="Live trades" value={d.live_trades} caption={`${d.backtest_trades} in the backtest`} icon={<Hash {...ico} />} />
      </StatGrid>

      <div className="dr-body">
        <section className="dr-card dr-zcard">
          <div className="dr-zgauge">
            <span className="lbl">Win-rate drift, z-score</span>
            <div
              className="zgauge"
              role="img"
              aria-label={`z-score ${d.z_score.toFixed(2)}`}
              title="Where the live win rate sits against the backtest, in standard deviations. Yellow: watch. Red: scale down."
            >
              <div className="rail" />
              <div className="pin" style={{ left: `calc(${Math.max(0, Math.min(100, ((d.z_score + 3) / 6) * 100))}% - 1px)` }} />
              <div className="ticks">
                {Z_TICKS.map((t, i) => (
                  <span key={t} style={{ left: `${(i / (Z_TICKS.length - 1)) * 100}%` }}>
                    {t}
                  </span>
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
        </section>

        <Card
          title="Live against the backtest"
          className="dr-chart-card"
          aside={
            d.curve.length ? (
              <div className="chart-keys">
                <span>
                  <b className="k-muted" />
                  BACKTEST EXPECTED ±1σ
                </span>
                <span>
                  <b className="k-accent" />
                  LIVE, CUMULATIVE R
                </span>
                <span>{d.live_trades} TRADES</span>
              </div>
            ) : undefined
          }
        >
          {d.curve.length ? (
            <div className="dr-chart">
              <div className="chart-wrap">
                <DriftChart d={d} />
              </div>
            </div>
          ) : (
            <Empty title="NO LIVE OUTCOMES YET">
              <span>The curve starts when the first live suggestion reaches its target, stop or 30-bar limit.</span>
            </Empty>
          )}
        </Card>
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

function StatsRow({ label, s, className }: { label: string; s: BacktestStats; className?: string }) {
  return (
    <tr className={className}>
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

function BacktestView({ tf }: { tf: '1d' | '4h' }) {
  const { data, isPending, error } = useBacktest(true)
  if (!data) return <QueryState isPending={isPending} error={error} what="the backtest" />
  // 4H and 1D are backtested apart; each keeps its own pooled and per-asset results.
  const part = data.timeframes?.[tf]
  if (!part?.pooled?.trades) return <QueryState isPending={false} error={new Error(`No ${tf.toUpperCase()} trades in the backtest yet.`)} what="the backtest" />
  return <BacktestBody key={tf} b={{ ...data, pooled: part.pooled, assets: part.assets }} />
}

function BacktestBody({ b }: { b: BacktestReport }) {
  const p = b.pooled
  const [lines] = useState(() => [{ points: dedupe(p.equity_r ?? []), color: 'accent', title: 'POOLED R', width: 2 as const }])
  const years = Object.entries(p.by_year).sort()
  return (
    <div className="dr-view dr-bt">
      <StatGrid>
        <StatCard
          label="Trades"
          value={p.trades}
          caption={`${p.by_direction.LONG.trades} long · ${p.by_direction.SHORT.trades} short`}
          icon={<Hash {...ico} />}
        />
        <StatCard label="Win rate" value={pct(p.win_rate)} caption="All assets pooled" icon={<Target {...ico} />} />
        <StatCard
          label="Avg R"
          value={r(p.avg_r, 3)}
          tone={statTone(p.avg_r)}
          caption="Per trade, in units of risk"
          icon={<TrendingUp {...ico} />}
          title="Average result per trade, in units of the risk taken"
        />
        <StatCard label="Total R" value={r(p.total_r, 1)} tone={statTone(p.total_r)} caption="Summed over every trade" icon={<ChartLine {...ico} />} />
        <StatCard
          label="Profit factor"
          value={p.profit_factor === null ? '—' : num(p.profit_factor, 2)}
          caption="Gross wins / gross losses"
          icon={<Scale {...ico} />}
        />
        <StatCard
          label="Max drawdown"
          value={r(p.max_drawdown_r, 1)}
          tone="down"
          caption="Deepest fall from a peak"
          icon={<TrendingDown {...ico} />}
        />
      </StatGrid>

      <div className="dr-body">
        <Note>
          {b.strategy}. Only divergences the model scored above the alert threshold out-of-sample (it never saw what came next) are traded: entry
          at the next open, stop at the swing extreme, target 2R, out after the timeframe's horizon, one trade at a time per asset, costs and
          slippage included. Run {day(b.generated_at)}.
        </Note>

        <Card title="By asset">
          <div className="tbl-wrap">
            <table className="tbl dr-tbl">
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
                <StatsRow label="ALL" s={p} className="dr-all" />
                {Object.entries(b.assets).map(([a, s]) => (
                  <StatsRow key={a} label={ASSET_META[a as keyof typeof ASSET_META]?.label ?? a} s={s} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="dr-bt-bottom">
          <Card
            title="Equity curve"
            className="dr-chart-card"
            aside={
              <div className="chart-keys">
                <span>
                  <b className="k-accent" />
                  CUMULATIVE R, ALL ASSETS
                </span>
              </div>
            }
          >
            <div className="dr-chart">
              <div className="chart-wrap">
                <Lines lines={lines} />
              </div>
            </div>
          </Card>
          <Card title="By year" className="dr-years">
            <div className="dr-fill">
              <div className="tbl-wrap">
                <table className="tbl dr-tbl">
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
          </Card>
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
    <div className="dr-view dr-fb">
      <StatGrid>
        <StatCard
          label="Learned from"
          value={c.n_backtest + c.n_live}
          caption={`${c.n_backtest} graded by the market + ${c.n_live} labelled by you`}
          icon={<Database {...ico} />}
        />
        <StatCard label="Plain rate" value={pct(c.base_win_rate)} caption="Share of divergences that worked: the baseline to beat" icon={<Percent {...ico} />} />
        <StatCard
          label="Out-of-sample Brier"
          value={o ? num(o.brier, 4) : '—'}
          caption={o ? `vs ${num(o.brier_base_rate, 4)} for the plain win rate; lower is better` : 'No out-of-sample check yet'}
          icon={<Gauge {...ico} />}
          title="Brier score on years the model hadn't seen (lower is better) vs always predicting the plain win rate"
        />
        <StatCard
          label="AUC"
          value={o?.auc == null ? '—' : num(o.auc, 2)}
          caption="Out of sample; 0.5 is a coin flip"
          icon={<Radar {...ico} />}
          title="How well the model ranks winners above losers on years it hadn't seen"
        />
        <StatCard
          label="Sets confidence?"
          value={c.skill ? 'YES' : 'NOT YET'}
          tone={c.skill ? 'up' : 'warn'}
          caption={c.skill ? 'Beat the plain rate on later data it hadn’t seen' : 'Scores shown as unproven until it does'}
          icon={c.skill ? <ShieldCheck {...ico} /> : <ShieldAlert {...ico} />}
        />
      </StatGrid>

      <div className="dr-body">
        <Note>
          {c.skill
            ? 'The model beat the plain rate on later divergences it had not seen, so its scores are trusted.'
            : `The model has not yet beaten the plain rate (${pct(c.base_win_rate)} of divergences worked) on later divergences it had not seen, so every score is shown as unproven. It retrains every hour on everything the market has graded plus your ✓/✗ (each counted 5×).`}
          {c.note ? ` ${c.note}` : ''} Trained {day(c.trained_at)}.
        </Note>

        <div className="dr-fb-grid">
          <Card title="Calibration, out of sample">
            <div className="tbl-wrap">
              <table className="tbl dr-tbl">
                <thead>
                  <tr>
                    <th className="l" title="Out-of-sample predictions, in fifths">
                      Predicted
                    </th>
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
          </Card>
          <Card title="Model weights">
            <div className="tbl-wrap">
              <table className="tbl dr-tbl">
                <thead>
                  <tr>
                    <th className="l">What the model looks at</th>
                    <th className="l" title="Standardised weight: right = more likely to win">
                      Effect on P(win)
                    </th>
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
          </Card>
        </div>
      </div>
    </div>
  )
}
