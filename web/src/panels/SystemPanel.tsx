import { useRuns, useSystem } from '../api/hooks'
import type { Components } from '../api/types'
import { Pill, QueryState } from '../components/bits'
import { RunControl } from '../components/RunControl'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { useNow } from '../hooks/useLiveFeed'
import { ago, day, hhmm, num } from '../lib/format'
import { useTerminal } from '../state/store'

const COMPONENT_TEXT: Record<keyof Components, string> = {
  runner: '24/7 runner (data + features every hour)',
  playbook: 'Transit playbook (scripts/build_playbook.py)',
  strategy: 'Strategy: trade suggestions',
  journal: 'Journal: decisions and outcomes',
  backtest: 'Backtest: expected performance for drift',
  alerts: 'Alerts: Telegram notifier',
}

export function SystemPanel({ hidden }: { hidden: boolean }) {
  const { data: sys, isPending, error } = useSystem()
  const now = useNow(1000)
  const connected = useTerminal((s) => s.feedConnected)

  return (
    <Panel code="SYS" title="System" hidden={hidden} meta={<span>RUNNER · LAYERS · FEEDS · LOG · CONFIG</span>}>
      {!sys ? (
        <QueryState isPending={isPending} error={error} what="system status" />
      ) : (
        <div className="sys">
          <section>
            <span className="lbl">Runner</span>
            <dl className="kv">
              <dt>State</dt>
              <dd className={sys.runner.state === 'LIVE' ? 'up' : 'down'}>● {sys.runner.state.replace('_', ' ')}</dd>
              {sys.runner.state === 'NEVER_RUN' ? (
                <>
                  <dt>Start it</dt>
                  <dd className="dim">uv run python -m orbit.runner.loop</dd>
                </>
              ) : (
                <>
                  <dt>Cycles</dt>
                  <dd>
                    {sys.runner.cycles}
                    {sys.runner.in_cycle ? ' · running now' : ''}
                  </dd>
                  <dt>Last cycle</dt>
                  <dd className={sys.runner.last_cycle_ok === false ? 'down' : ''}>
                    {sys.runner.last_cycle_finished_at ? `${ago(sys.runner.last_cycle_finished_at, now)} ago · ${sys.runner.last_cycle_ok ? 'ok' : 'failed'}` : '—'}
                  </dd>
                  {sys.runner.last_error && (
                    <>
                      <dt>Error</dt>
                      <dd className="down">{sys.runner.last_error}</dd>
                    </>
                  )}
                  <dt>Next cycle</dt>
                  <dd className="hi">
                    {sys.runner.next_cycle_at ? (Date.parse(sys.runner.next_cycle_at) > now ? `in ${ago(now - (Date.parse(sys.runner.next_cycle_at) - now), now)}` : 'due') : '—'}
                  </dd>
                </>
              )}
              <dt>Auto-execution</dt>
              <dd>
                <Pill tone="off">{sys.auto_execution ? 'ON' : 'OFF · LOCKED'}</Pill>
              </dd>
            </dl>
          </section>
          <section>
            <span className="lbl">Layers</span>
            <dl className="kv">
              {(Object.keys(COMPONENT_TEXT) as (keyof Components)[]).map((k) => (
                <div key={k} className="kv-row">
                  <dt>{COMPONENT_TEXT[k]}</dt>
                  <dd className={sys.components[k] ? 'up' : 'dim'}>{sys.components[k] ? 'BUILT' : 'NOT BUILT'}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="wide">
            <span className="lbl">Analysis runs · button here, on ASTRO → PLAYBOOK, or the runner's daily schedule</span>
            <RunControl />
            <RunHistory />
          </section>
          <section className="wide">
            <span className="lbl">Price feeds · live stream {connected ? 'connected' : 'disconnected'}</span>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th className="l">Asset</th>
                    <th className="l">Stored history from</th>
                    <th>First bar</th>
                    <th>Last bar</th>
                    <th>Bars</th>
                    <th className="l">Live</th>
                    <th>Last tick</th>
                  </tr>
                </thead>
                <tbody>
                  {sys.feeds.map((f) => (
                    <tr key={f.asset}>
                      <td className="l strong">{ASSET_META[f.asset].label}</td>
                      <td className="l">{f.sources.join(' → ') || <span className="dim">no history stored</span>}</td>
                      <td>{f.first_bar ? `${day(f.first_bar)} ${new Date(f.first_bar).getUTCFullYear()}` : '—'}</td>
                      <td>{f.last_bar ? day(f.last_bar) : '—'}</td>
                      <td>{num(f.bars, 0)}</td>
                      <td className="l">
                        <Pill tone={f.live_source === 'LIVE' ? 'ok' : f.live_source === 'DELAYED' ? 'watch' : 'off'}>{f.live_source}</Pill>
                      </td>
                      <td className={f.last_tick_at ? 'up' : 'dim'}>{f.last_tick_at ? `${ago(f.last_tick_at, now)} ago` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section>
            <span className="lbl">Runner log · data/logs/runner.log</span>
            {sys.log.length ? (
              <div className="log">
                {sys.log.slice(0, 14).map((l, i) => (
                  <div key={i}>
                    <span className="dim">{hhmm(l.timestamp)}</span>
                    <span className={l.level === 'ERROR' ? 'ALERT' : l.level}>{l.level}</span>
                    <span>{l.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="dim">No log lines yet.</p>
            )}
          </section>
          <section>
            <span className="lbl">Config · config/settings.py · read-only</span>
            <dl className="kv">
              {Object.entries(sys.config).map(([k, v]) => (
                <div key={k} className="kv-row">
                  <dt>{k}</dt>
                  <dd className={v === 'not set' ? 'dim' : ''}>{v}</dd>
                </div>
              ))}
              <div className="kv-row">
                <dt>Playbook built</dt>
                <dd className={sys.playbook_generated_at ? '' : 'dim'}>{sys.playbook_generated_at ? `${day(sys.playbook_generated_at)} ${hhmm(sys.playbook_generated_at)}` : 'never'}</dd>
              </div>
            </dl>
          </section>
        </div>
      )}
    </Panel>
  )
}

function RunHistory() {
  const { data } = useRuns()
  if (!data?.length) return null
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th className="l">Started (UTC)</th>
            <th className="l">Trigger</th>
            <th className="l">Status</th>
            <th>Took</th>
            <th>Tests</th>
            <th className="l">Placebo</th>
            <th>Changes</th>
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 10).map((r) => {
            const took = r.finished_at && r.started_at ? Math.round((Date.parse(r.finished_at) - Date.parse(r.started_at)) / 1000) : null
            return (
              <tr key={r.id} title={r.error ?? r.step}>
                <td className="l">
                  {day(r.created_at)} {hhmm(r.created_at)}
                </td>
                <td className="l">{r.trigger}</td>
                <td className={`l ${r.status === 'succeeded' ? 'up' : r.status === 'failed' ? 'down' : 'hi'}`}>{r.status}</td>
                <td>{took === null ? '—' : took < 90 ? `${took}s` : `${Math.round(took / 60)} min`}</td>
                <td>{r.summary.total_tests ? num(r.summary.total_tests, 0) : '—'}</td>
                <td className="l">
                  {r.summary.placebo ? `${r.summary.placebo.runs_with_any_discovery}/${r.summary.placebo.placebo_runs} false` : r.include_placebo ? '…' : '—'}
                </td>
                <td>{r.status === 'succeeded' ? r.changes.length : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
