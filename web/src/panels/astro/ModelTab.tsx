import { useModel } from '../../api/hooks'
import type { Asset, ModelReport } from '../../api/types'
import { Empty, Pill, QueryState } from '../../components/bits'
import { num, pct } from '../../lib/format'

const TARGET: Record<string, string> = { big_up: 'Big up move', big_down: 'Big down move', sideways: 'Sideways' }
const verdictTone = (v: string) => (v === 'adds skill' ? 'ok' : v === 'unclear' ? 'watch' : 'off')

/** Does knowing the Vedic sky make a price-only forecast better? */
export function ModelTab({ asset }: { asset: Asset }) {
  const { data, isPending, error } = useModel(asset)
  if (!data) {
    if (isPending || !error) return <QueryState isPending={isPending} error={error} what="the Vedic model" />
    return (
      <Empty title="NOT EVALUATED YET">
        <span>The Vedic model is evaluated on every analysis run. Press RUN ANALYSIS on SYS (F8), or wait for the 00:30 UTC run.</span>
      </Empty>
    )
  }
  return <ModelView m={data} />
}

function ModelView({ m }: { m: ModelReport }) {
  const rows = Object.entries(m.results)
  return (
    <>
      <div className="pbk-tools">
        <span className="dim">
          Two forecasters trained walk-forward (retrained every {m.retrain_years} years, always tested on the years after): one sees price only (
          {m.tech_features.length} features), the other also sees {m.vedic_features} Vedic states. The sky only gets credit if it beats price alone{' '}
          <b>and</b> beats the same Vedic data shifted by years (controls that can't know anything). As of {m.as_of}.
        </span>
      </div>
      <div className="model-summary">
        <b>{m.summary}</b>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th className="l">Target</th>
              <th>Horizon</th>
              <th>Base rate</th>
              <th title="1 − log loss / always-guess-the-base-rate log loss. Above 0 = better than guessing.">Skill · price only</th>
              <th>Skill · + Vedic</th>
              <th title="How much the misaligned-Vedic controls improved on price only. Vedic must beat these.">Controls</th>
              <th title="Years in which adding Vedic helped">Years better</th>
              <th className="l">Verdict</th>
              <th title="Today's forecast: price only / with Vedic">Today</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, r]) => {
              const tech = r.scores.TECH
              const vedic = r.scores['TECH+VEDIC']
              const fc = m.forecast[key]
              return (
                <tr key={key}>
                  <td className="l strong">{TARGET[r.target] ?? r.target}</td>
                  <td>{r.horizon_days}d</td>
                  <td className="mid">{pct(r.base_rate)}</td>
                  <td className={tech.skill > 0 ? 'up' : 'mid'}>{num(tech.skill * 100, 1)}%</td>
                  <td className={vedic.skill > tech.skill ? 'up' : 'mid'}>{num(vedic.skill * 100, 1)}%</td>
                  <td className="mid">{r.control_log_loss_gains.map((g) => (g >= 0 ? '+' : '') + num(g * 1000, 1)).join(' · ')}</td>
                  <td>
                    {r.years_vedic_better}/{r.years}
                  </td>
                  <td className="l">
                    <Pill tone={verdictTone(r.verdict)}>{r.verdict.toUpperCase()}</Pill>
                  </td>
                  <td>{fc ? `${pct(fc.TECH)} / ${pct(fc['TECH+VEDIC'])}` : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <details className="model-weights">
        <summary>Vedic states the model leaned on most (only meaningful where the verdict is ADDS SKILL)</summary>
        {rows.map(([key, r]) =>
          r.top_vedic_features?.length ? (
            <div key={key} className="mw">
              <span className="lbl">
                {TARGET[r.target]} · {r.horizon_days}d
              </span>
              <ul>
                {r.top_vedic_features.slice(0, 5).map((f) => (
                  <li key={f.state}>
                    <span className={f.weight > 0 ? 'up' : 'down'}>{f.weight > 0 ? '▲' : '▼'}</span> {f.description}
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}
      </details>
    </>
  )
}
