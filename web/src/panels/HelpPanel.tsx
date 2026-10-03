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

export function HelpPanel({ hidden }: { hidden: boolean }) {
  return (
    <Panel code="HELP" title="Commands and keys" hidden={hidden}>
      <div className="help">
        <section>
          <h3>INSTRUMENT SEARCH</h3>
          <p>The search box at the top finds an instrument by code, name or pair. ↑ and ↓ pick one, Enter or a click makes it the active asset. Screens are on the bar at the bottom, the F-keys, and Ctrl K.</p>
          <table>
            <tbody>
              {EXAMPLES.map(([k, d]) => (
                <tr key={k}>
                  <td>
                    <kbd className="k">{k}</kbd>
                  </td>
                  <td>{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h3>FUNCTIONS</h3>
          <table>
            <tbody>
              {FUNCTIONS.map((f) => (
                <tr key={f.code}>
                  <td>
                    <kbd className="k">{f.code}</kbd>
                  </td>
                  <td>
                    <kbd className="k">{f.key}</kbd>
                  </td>
                  <td>{f.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h3>KEYS</h3>
          <table>
            <tbody>
              {KEYS.map(([k, d]) => (
                <tr key={k}>
                  <td>
                    <kbd className="k">{k}</kbd>
                  </td>
                  <td>{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h3>WHERE THE DATA COMES FROM</h3>
          <p>
            Everything is real. Stored daily history is stitched from Bitstamp and Coinbase (early BTC and ETH) and Binance. Silver is
            Dukascopy spot (XAG/USD, 2003 on) once its one-time download completes (scripts/backfill_silver.py); until then it is Yahoo
            futures. SYS (F8) shows which source each asset is on. Live prices stream from Binance every few seconds; silver's are delayed. Graha positions come
            from NASA JPL's DE421 ephemeris, converted to the sidereal zodiac (Lahiri / Chitrapaksha ayanamsa).
          </p>
          <p>Screens for reports that haven't been generated yet say so instead of showing anything made up.</p>
        </section>
        <section>
          <h3>TRANSIT PLAYBOOK (ASTRO)</h3>
          <p>
            Vedic rules only. For each asset, every graha's rashi and nakshatra changes, vakri and margi stations, yuti, drishti (7th plus the
            special aspects of Mangal, Guru, Shani and the nodes), asta, graha yuddha, amavasya, purnima, grahan and the named yogas are scored
            against what followed: a big move (the asset's own top or bottom 15%), a sideways stretch, or neither. Each pattern is tested against
            a shifted version of its own calendar, then corrected for how many tests were run.
          </p>
          <p>
            STRONG and MODERATE survive that correction; WEAK doesn't; TOO FEW (under 12 occurrences) is never tested. Placebo runs on fake
            calendars check that the method isn't finding patterns in noise.
          </p>
          <p>
            MODEL goes further: a forecaster that sees every Vedic state at once, trained walk-forward, only credited if it beats price alone and
            beats the same sky shifted by years.
          </p>
        </section>
        <section>
          <h3>CHART</h3>
          <p>LIVE streams TradingView's own market data through their embedded chart, with their drawing tools and intervals.</p>
          <p>
            ORBIT draws Orbit's full stored history with every RSI divergence (the strategy's signals), regime flips and Vedic markers (stations,
            eclipses, slow rashi changes); circles mark events the playbook rates for this asset. TradingView's widget can't show those.
          </p>
        </section>
        <section>
          <h3>HOW ORBIT DECIDES</h3>
          <p>
            One strategy runs: RSI(14) divergence on daily bars. A lower price low with a higher RSI low is bullish; a higher high with a lower RSI
            high is bearish. Stop beyond the swing, target 2R, out after 30 bars. It is backtested on the full history every analysis run.
          </p>
          <p>
            Confidence comes from the feedback loop: a model of which divergences actually worked, retrained on every run with the backtest plus
            every live outcome. It only sets confidence once it beats the plain win rate out-of-sample; until then confidence is that win rate.
          </p>
          <p>
            Nothing executes on its own. You take, skip or modify every suggestion, and each decision goes to the journal. Every suggestion is
            followed to its outcome whether you took it or not. Drift compares live results with the backtest.
          </p>
        </section>
      </div>
    </Panel>
  )
}
