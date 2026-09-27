import { useAstro } from '../api/hooks'
import { Pill } from '../components/bits'
import { Panel } from '../components/Panel'
import { useNow } from '../hooks/useLiveFeed'
import { day, signed, tone } from '../lib/format'

const DAY = 86_400_000

export function AstroPanel({ hidden }: { hidden: boolean }) {
  const { data = [], isError, error } = useAstro()
  const now = useNow(60_000)
  const today = now - (now % DAY)
  const next = data.find((e) => Date.parse(e.timestamp) >= today)

  return (
    <Panel code="ASTRO" title="Transit calendar" hidden={hidden} meta={<span>RESEARCH TRACK</span>}>
      <div className="astro-banner">
        <Pill tone="astro">RESEARCH</Pill>
        <span>
          Transits are recorded and studied here. They can nudge a suggestion's confidence by at most 0.15 and never size a trade. Dates are placeholders until the ephemeris feed is connected.
        </span>
      </div>
      {isError && <p className="load-err">Couldn't load transits: {String(error)}</p>}
      <div className="tbl-wrap">
        <table className="tbl tl">
          <thead>
            <tr>
              <th className="l">Date</th>
              <th>T±</th>
              <th className="l">Body</th>
              <th className="l">Event</th>
              <th>Prior occurrences</th>
              <th>BTC 5D mean after</th>
              <th className="l">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => {
              const d = Math.round((Date.parse(e.timestamp) - today) / DAY)
              return (
                <tr key={e.id} className={`${d < 0 ? 'past' : ''} ${e === next ? 'next' : ''}`}>
                  <td className="l">{day(e.timestamp)}</td>
                  <td>{d > 0 ? `T−${d}D` : d === 0 ? 'TODAY' : `T+${-d}D`}</td>
                  <td className="l body">{e.body}</td>
                  <td className="l">{e.event}</td>
                  <td>{e.prior_occurrences}</td>
                  <td className={e.btc_5d_mean_after === null ? 'dim' : tone(e.btc_5d_mean_after)}>{e.btc_5d_mean_after === null ? 'n/a' : `${signed(e.btc_5d_mean_after, 1)}%`}</td>
                  <td className="l dim">{e.prior_occurrences < 8 ? 'SAMPLE TOO SMALL' : 'IN STUDY'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
