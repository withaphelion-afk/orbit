import { useSystem } from '../api/hooks'
import { Pill } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { useNow } from '../hooks/useLiveFeed'
import { day, hhmm } from '../lib/format'
import { useTerminal } from '../state/store'

export function SystemPanel({ hidden }: { hidden: boolean }) {
  const { data: sys, isError, error } = useSystem()
  const now = useNow(1000)
  const lastTickAt = useTerminal((s) => s.lastTickAt)
  const connected = useTerminal((s) => s.feedConnected)

  const left = sys ? Math.max(0, Date.parse(sys.next_eval) - now) : 0
  const h = Math.floor(left / 3_600_000)
  const m = Math.floor((left % 3_600_000) / 60_000)

  return (
    <Panel code="SYS" title="System" hidden={hidden} meta={<span>RUNNER · FEEDS · ALERTS · CONFIG</span>}>
      {isError && <p className="load-err">Couldn't reach the runner: {String(error)}</p>}
      {sys && (
        <div className="sys">
          <section>
            <span className="lbl">Runner</span>
            <dl className="kv">
              <dt>Status</dt>
              <dd className={sys.runner === 'LIVE' ? 'up' : 'down'}>● {sys.runner}</dd>
              <dt>Strategy</dt>
              <dd>{sys.strategy} · one active</dd>
              <dt>Timeframe</dt>
              <dd>{sys.timeframe.toUpperCase()}</dd>
              <dt>Last evaluation</dt>
              <dd>
                {day(sys.last_eval)} {hhmm(sys.last_eval)}
              </dd>
              <dt>Next evaluation</dt>
              <dd className="hi">
                in {h}h {String(m).padStart(2, '0')}m
              </dd>
              <dt>Auto-execution</dt>
              <dd>
                <Pill tone="off">{sys.auto_execution ? 'ON' : 'OFF · LOCKED'}</Pill>
              </dd>
            </dl>
          </section>
          <section>
            <span className="lbl">Data feeds · tick stream {connected ? 'connected' : 'disconnected'}</span>
            <table className="tbl">
              <thead>
                <tr>
                  <th className="l">Asset</th>
                  <th className="l">Source</th>
                  <th>Last bar</th>
                  <th>Last tick</th>
                </tr>
              </thead>
              <tbody>
                {sys.feeds.map((f) => (
                  <tr key={f.asset}>
                    <td className="l">{ASSET_META[f.asset].label}</td>
                    <td className="l">
                      <Pill tone={f.source === 'LIVE' ? 'ok' : 'mock'}>{f.source}</Pill>
                    </td>
                    <td>{day(f.last_bar)}</td>
                    <td className={connected ? 'up' : 'down'}>{lastTickAt ? `${Math.round((now - lastTickAt) / 1000)}s` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section>
            <span className="lbl">Alert log · Telegram {sys.config.TELEGRAM_BOT_TOKEN === 'not set' ? 'not configured' : 'configured'}</span>
            <div className="log">
              {sys.alerts.slice(0, 12).map((a, i) => (
                <div key={i}>
                  <span className="dim">{hhmm(a.timestamp)}</span>
                  <span className={a.level}>{a.level}</span>
                  <span>{a.message}</span>
                </div>
              ))}
            </div>
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
            </dl>
          </section>
        </div>
      )}
    </Panel>
  )
}
