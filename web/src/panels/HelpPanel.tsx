import { Panel } from '../components/Panel'
import { FUNCTIONS } from '../lib/commands'

const EXAMPLES = [
  ['SOL GP', 'Chart Solana'],
  ['BTC', 'Make Bitcoin the active asset'],
  ['SUGG', 'Open the suggestion queue'],
  ['XAG DRIFT', 'Switch to silver and open Drift'],
]

const KEYS = [
  ['CTRL K', 'Command palette'],
  ['/', 'Focus the command line'],
  ['1 – 4', 'Switch asset: BTC ETH SOL XAG'],
  ['J / K', 'Next or previous suggestion (SUGG)'],
  ['T  S  M', 'Take, skip or modify the selected suggestion'],
  ['CTRL ↵', 'Log the decision'],
  ['ESC', 'Cancel or close, then return to MON'],
  ['Click a panel code', 'Maximise that panel; click again to restore'],
]

export function HelpPanel({ hidden }: { hidden: boolean }) {
  return (
    <Panel code="HELP" title="Commands and keys" hidden={hidden}>
      <div className="help">
        <section>
          <h3>COMMAND LINE</h3>
          <p>Type an asset, a function, or both, then press Enter or GO. Tab completes the grey suggestion. ↑ and ↓ step through history.</p>
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
            Everything is real. Stored daily history is stitched from Bitstamp and Coinbase (early BTC and ETH) and Binance, and silver comes
            from Yahoo futures. Live prices stream from Binance every few seconds; silver's are delayed. Planet positions come from NASA JPL's
            DE421 ephemeris.
          </p>
          <p>Screens for layers that aren't built yet (strategy, journal, backtest) say so instead of showing anything made up.</p>
        </section>
        <section>
          <h3>TRANSIT PLAYBOOK (ASTRO)</h3>
          <p>
            For each asset, every sign ingress and retrograde station is scored against what followed it: a big move (the asset's own top or
            bottom 15%), a sideways stretch, or neither. Each pattern is tested against a shifted version of its own calendar, then corrected
            for how many tests were run.
          </p>
          <p>
            STRONG and MODERATE survive that correction; WEAK doesn't; TOO FEW (under 12 occurrences) is never tested. Placebo runs on fake
            calendars check that the method isn't finding patterns in noise.
          </p>
        </section>
        <section>
          <h3>CHART</h3>
          <p>LIVE streams TradingView's own market data through their embedded chart, with their drawing tools and intervals.</p>
          <p>ORBIT draws Orbit's full stored history with regime flips and transit markers; circles mark transits the playbook rates for this asset. TradingView's widget can't show those.</p>
        </section>
        <section>
          <h3>HOW ORBIT DECIDES</h3>
          <p>One strategy runs at a time. Each suggestion lists the signals behind it and how strongly each one agrees. Signals that disagree are marked AGAINST and pull confidence down.</p>
          <p>Nothing executes on its own. You take, skip or modify every suggestion, and each decision goes to the journal. Drift compares live results with the backtest and scales Orbit down when the two diverge.</p>
        </section>
      </div>
    </Panel>
  )
}
