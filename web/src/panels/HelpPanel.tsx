import type { ReactNode } from 'react'
import { ChartCandlestick, Database, Keyboard, LayoutGrid, Scale, Search, Sparkles } from 'lucide-react'
import { Panel } from '../components/Panel'
import { FUNCTIONS } from '../lib/commands'

const EXAMPLES = [
  ['btc', 'Bitcoin'],
  ['silver  or  xag', 'Silver (XAG/USD)'],
  ['usd', 'Every instrument'],
]

const KEYS = [
  ['CTRL K', 'Command palette'],
  ['/', 'Search an instrument (or just start typing)'],
  ['1 – 4', 'Switch asset: BTC ETH SOL XAG'],
  ['J / K', 'Next or previous suggestion (SUGG)'],
  ['T  S  M', 'Take, skip or modify the selected suggestion'],
  ['CTRL ↵', 'Log the decision'],
  ['ESC', 'Cancel or close, then return to MON'],
]

const ICON = { size: 16, strokeWidth: 1.75 } as const

/** Words that join two keys ("J / K", "1 – 4", "silver or xag") rather than being keys themselves. */
const JOINERS = new Set(['/', '–', 'or'])

/** A key or key sequence as separate key caps: "CTRL K" becomes two caps, "J / K" two caps with the slash between. */
function Keys({ k }: { k: string }) {
  const parts = k.split(/\s+/).filter(Boolean)
  return (
    <span className="keys">
      {parts.map((p, i) =>
        parts.length > 1 && JOINERS.has(p) ? (
          <span key={`${i}${p}`} className="keys-join">
            {p}
          </span>
        ) : (
          <kbd key={`${i}${p}`} className="k">
            {p}
          </kbd>
        ),
      )}
    </span>
  )
}

function Card({ icon, title, className, children }: { icon: ReactNode; title: string; className?: string; children: ReactNode }) {
  return (
    <section className={className ? `help-card ${className}` : 'help-card'}>
      <header className="help-card-h">
        <span className="help-ico" aria-hidden="true">
          {icon}
        </span>
        <h4>{title}</h4>
      </header>
      {children}
    </section>
  )
}

export function HelpPanel({ hidden }: { hidden: boolean }) {
  return (
    <Panel
      code="HELP"
      title="Commands and keys"
      description="How to get around Orbit, what each screen is for, and where its data and suggestions come from."
      hidden={hidden}
    >
      <div className="help">
        <div className="help-group">
          <h3 className="help-group-h">Getting around</h3>
          <div className="help-grid nav">
            <Card icon={<Search {...ICON} />} title="Instrument search" className="help-search">
              <p>
                The search box at the top finds an instrument by code, name or pair. <kbd className="k">↑</kbd> and <kbd className="k">↓</kbd> pick one,{' '}
                <kbd className="k">Enter</kbd> or a click makes it the active asset. Screens are on the bar at the bottom, the F-keys, and{' '}
                <Keys k="Ctrl K" />.
              </p>
              <table className="help-tbl">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Finds</th>
                  </tr>
                </thead>
                <tbody>
                  {EXAMPLES.map(([k, d]) => (
                    <tr key={k}>
                      <td className="kc">
                        <Keys k={k} />
                      </td>
                      <td className="d">{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card icon={<LayoutGrid {...ICON} />} title="Functions">
              <table className="help-tbl">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Screen</th>
                    <th>What it is</th>
                  </tr>
                </thead>
                <tbody>
                  {FUNCTIONS.map((f) => (
                    <tr key={f.code}>
                      <td className="kc">
                        <kbd className="k">{f.key}</kbd>
                      </td>
                      <td className="fn" title={`On the bar at the bottom as ${f.label}; type ${f.code} in Ctrl K`}>
                        <span className="fn-label">{f.label}</span>{' '}
                        <code className="fn-code">{f.code}</code>
                      </td>
                      <td className="d">{f.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card icon={<Keyboard {...ICON} />} title="Keys">
              <table className="help-tbl">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Does</th>
                  </tr>
                </thead>
                <tbody>
                  {KEYS.map(([k, d]) => (
                    <tr key={k}>
                      <td className="kc">
                        <Keys k={k} />
                      </td>
                      <td className="d">{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        </div>

        <div className="help-group">
          <h3 className="help-group-h">How Orbit works</h3>
          <div className="help-grid prose">
            <Card icon={<Database {...ICON} />} title="Where the data comes from">
              <p>
                Everything is real. Stored daily history is stitched from Bitstamp and Coinbase (early BTC and ETH) and Binance. Silver is
                Dukascopy spot (XAG/USD, 2003 on) once its one-time download completes (<code>scripts/backfill_silver.py</code>); until then it is
                Yahoo futures. <b>SYS (F8)</b> shows which source each asset is on. Live prices stream from Binance every few seconds; silver's are
                delayed. Graha positions come from NASA JPL's DE421 ephemeris, converted to the sidereal zodiac (Lahiri / Chitrapaksha ayanamsa).
              </p>
              <p>Screens for reports that haven't been generated yet say so instead of showing anything made up.</p>
            </Card>

            <Card icon={<Sparkles {...ICON} />} title="Transit playbook (ASTRO)" className="help-astro">
              <p>
                Vedic rules only. For each asset, every graha's rashi and nakshatra changes, vakri and margi stations, yuti, drishti (7th plus the
                special aspects of Mangal, Guru, Shani and the nodes), asta, graha yuddha, amavasya, purnima, grahan and the named yogas are scored
                against what followed: a big move (the asset's own top or bottom 15%), a sideways stretch, or neither. Each pattern is tested against
                a shifted version of its own calendar, then corrected for how many tests were run.
              </p>
              <p>
                <b>STRONG</b> and <b>MODERATE</b> survive that correction; <b>WEAK</b> doesn't; <b>TOO FEW</b> (under 12 occurrences) is never
                tested. Placebo runs on fake calendars check that the method isn't finding patterns in noise.
              </p>
              <p>
                <b>MODEL</b> goes further: a forecaster that sees every Vedic state at once, trained walk-forward, only credited if it beats price
                alone and beats the same sky shifted by years.
              </p>
            </Card>

            <Card icon={<ChartCandlestick {...ICON} />} title="Chart">
              <p>
                <b>LIVE</b> streams TradingView's own market data through their embedded chart, with their drawing tools and intervals.
              </p>
              <p>
                <b>ORBIT</b> draws Orbit's full stored history with every RSI divergence (the strategy's signals), regime flips and Vedic markers
                (stations, eclipses, slow rashi changes); circles mark events the playbook rates for this asset. TradingView's widget can't show
                those.
              </p>
            </Card>

            <Card icon={<Scale {...ICON} />} title="How Orbit decides">
              <p>
                One strategy runs: RSI(14) divergence on daily bars. A lower price low with a higher RSI low is bullish; a higher high with a lower
                RSI high is bearish. Stop beyond the swing, target 2R, out after 30 bars. It is backtested on the full history every analysis run.
              </p>
              <p>
                Confidence comes from the feedback loop: a model of which divergences actually worked, retrained on every run with the backtest plus
                every live outcome. It only sets confidence once it beats the plain win rate out-of-sample; until then confidence is that win rate.
              </p>
              <p>
                Nothing executes on its own. You take, skip or modify every suggestion, and each decision goes to the journal. Every suggestion is
                followed to its outcome whether you took it or not. Drift compares live results with the backtest.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </Panel>
  )
}
