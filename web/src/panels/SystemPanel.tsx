import {
  Activity,
  CalendarClock,
  CircleCheck,
  CircleDashed,
  FlaskConical,
  History,
  Layers,
  Lock,
  LockOpen,
  Radio,
  RefreshCw,
  ScrollText,
  SlidersHorizontal,
  Terminal,
  Timer,
  TriangleAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useRuns, useSchedule, useSystem } from '../api/hooks'
import type { Components, ScheduleView, SystemStatus } from '../api/types'
import { Pill, QueryState, StatCard, StatGrid } from '../components/bits'
import { RunControl } from '../components/RunControl'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { useNow } from '../hooks/useLiveFeed'
import { ago, day, hhmm, num } from '../lib/format'
import { useTerminal } from '../state/store'

const LAYERS: Record<keyof Components, { name: string; detail: string }> = {
  runner: { name: '24/7 runner', detail: 'data + features every hour' },
  playbook: { name: 'Transit playbook', detail: 'scripts/build_playbook.py' },
  strategy: { name: 'Strategy', detail: 'trade suggestions' },
  journal: { name: 'Journal', detail: 'decisions and outcomes' },
  backtest: { name: 'Backtest', detail: 'expected performance for drift' },
  alerts: { name: 'Alerts', detail: 'Telegram notifier' },
}
const LAYER_KEYS = Object.keys(LAYERS) as (keyof Components)[]

const ICON = { size: 18, strokeWidth: 1.75 } as const
const SMALL = { size: 16, strokeWidth: 1.75 } as const

/** "in 12m" while `at` is ahead, "due" once it has passed. */
function until(at: string, now: number): string {
  const t = Date.parse(at)
  return t > now ? `in ${ago(now - (t - now), now)}` : 'due'
}

const stamp = (t: string) => `${day(t)} ${hhmm(t)}`

function every(seconds: number): string {
  if (seconds % 3600 === 0) return seconds === 3600 ? 'every hour' : `every ${seconds / 3600} hours`
  return seconds >= 60 ? `every ${Math.round(seconds / 60)} min` : `every ${seconds}s`
}

function logTone(level: string): string {
  if (level === 'ERROR' || level === 'CRITICAL' || level === 'ALERT') return 'lv-err'
  if (level === 'WARNING' || level === 'WARN') return 'lv-warn'
  return 'lv-info'
}

export function SystemPanel({ hidden }: { hidden: boolean }) {
  const { data: sys, isPending, error } = useSystem()
  const schedule = useSchedule()
  const now = useNow(1000)
  const connected = useTerminal((s) => s.feedConnected)

  return (
    <Panel
      code="SYS"
      title="System"
      description="Whether the 24/7 runner, the price feeds and the analysis runs are healthy, with the runner's log and the settings it runs on."
      hidden={hidden}
    >
      {!sys ? (
        <QueryState isPending={isPending} error={error} what="system status" />
      ) : (
        <div className="sys">
          <RunnerStats sys={sys} sched={schedule.data} schedPending={schedule.isPending} now={now} />

          {sys.runner.state === 'NEVER_RUN' ? (
            <p className="sys-note">
              <Terminal {...SMALL} />
              <span>
                The runner has never run. Start it with <code>uv run python -m orbit.runner.loop</code>
              </span>
            </p>
          ) : sys.runner.last_error ? (
            <p className="sys-note bad">
              <TriangleAlert {...SMALL} />
              <span>
                <b>Last error</b> {sys.runner.last_error}
              </span>
            </p>
          ) : null}

          <div className="sys-grid">
            <Card
              area="layers"
              icon={<Layers {...SMALL} />}
              title="Layers"
              note="What the backend has built so far"
              aside={`${LAYER_KEYS.filter((k) => sys.components[k]).length} of ${LAYER_KEYS.length} built`}
            >
              <ul className="sys-layers-list">
                {LAYER_KEYS.map((k) => {
                  const built = sys.components[k]
                  return (
                    <li key={k} className={built ? 'on' : ''}>
                      {built ? <CircleCheck {...SMALL} className="up" /> : <CircleDashed {...SMALL} className="dim" />}
                      <span className="sys-layer">
                        <b>{LAYERS[k].name}</b>
                        <span>{LAYERS[k].detail}</span>
                      </span>
                      <em className={built ? 'up' : 'dim'}>{built ? 'BUILT' : 'NOT BUILT'}</em>
                    </li>
                  )
                })}
              </ul>
            </Card>

            <Card
              area="feeds"
              icon={<Radio {...SMALL} />}
              title="Price feeds"
              note="Stored history and the live price for each asset"
              aside={
                <span className="sys-live" title="The live price stream from the API to this browser">
                  <i className={`dot ${connected ? '' : 'bad'}`} aria-hidden="true" />
                  Live stream {connected ? 'connected' : 'disconnected'}
                </span>
              }
            >
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
                        <td className="l">
                          <b className="sys-asset">{ASSET_META[f.asset].label}</b>
                          <span className="dim">{ASSET_META[f.asset].name}</span>
                        </td>
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
            </Card>

            <Card
              area="runs"
              icon={<FlaskConical {...SMALL} />}
              title="Analysis runs"
              note="Start one here, on ASTRO → PLAYBOOK, or let the runner's daily schedule do it"
            >
              <div className="sys-runctl">
                <RunControl />
              </div>
              <RunHistory />
            </Card>

            <Card
              area="log"
              icon={<ScrollText {...SMALL} />}
              title="Runner log"
              note={<code>data/logs/runner.log</code>}
              aside={sys.log.length ? 'Newest first' : undefined}
            >
              {sys.log.length ? (
                <ol className="sys-log">
                  {sys.log.slice(0, 14).map((l, i) => (
                    <li key={i} className={logTone(l.level)}>
                      <time dateTime={l.timestamp}>{hhmm(l.timestamp)}</time>
                      <em>{l.level}</em>
                      <span>{l.message}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="sys-none">No log lines yet.</p>
              )}
            </Card>

            <Card
              area="config"
              icon={<SlidersHorizontal {...SMALL} />}
              title="Config"
              note={
                <>
                  <code>config/settings.py</code> · read-only
                </>
              }
            >
              <dl className="sys-kv">
                {Object.entries(sys.config).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd className={v === 'not set' ? 'dim' : ''}>{v}</dd>
                  </div>
                ))}
                <div className="meta">
                  <dt>Playbook built</dt>
                  <dd className={sys.playbook_generated_at ? '' : 'dim'}>{sys.playbook_generated_at ? stamp(sys.playbook_generated_at) : 'never'}</dd>
                </div>
              </dl>
            </Card>
          </div>
        </div>
      )}
    </Panel>
  )
}

function RunnerStats({ sys, sched, schedPending, now }: { sys: SystemStatus; sched: ScheduleView | undefined; schedPending: boolean; now: number }) {
  const r = sys.runner
  const never = r.state === 'NEVER_RUN'
  return (
    <StatGrid>
      <StatCard
        label="Runner"
        icon={<Activity {...ICON} />}
        value={r.state.replace('_', ' ')}
        tone={r.state === 'LIVE' ? 'up' : 'down'}
        caption={never ? 'Not started yet' : r.state === 'STALE' ? "Hasn't checked in on time" : r.started_at ? `Started ${stamp(r.started_at)}` : undefined}
        title="LIVE: the runner checked in recently. STALE: nothing from it for over two cycle intervals plus ten minutes. NEVER RUN: no runner status found."
      />
      {!never && (
        <>
          <StatCard
            label="Cycles"
            icon={<RefreshCw {...ICON} />}
            value={num(r.cycles, 0)}
            caption={r.in_cycle ? 'Running one now' : r.interval_seconds ? `One ${every(r.interval_seconds)}` : undefined}
            title="Data and feature cycles the runner has completed since it started"
          />
          <StatCard
            label="Last cycle"
            icon={<History {...ICON} />}
            value={r.last_cycle_finished_at ? `${ago(r.last_cycle_finished_at, now)} ago` : '—'}
            tone={r.last_cycle_ok === false ? 'down' : undefined}
            caption={!r.last_cycle_finished_at ? 'None finished yet' : r.last_cycle_ok ? 'Finished OK' : <span className="down">Failed</span>}
            title={r.last_cycle_finished_at ? `Finished ${stamp(r.last_cycle_finished_at)}` : undefined}
          />
          <StatCard
            label="Next cycle"
            icon={<Timer {...ICON} />}
            value={r.next_cycle_at ? until(r.next_cycle_at, now) : '—'}
            caption={r.next_cycle_at ? stamp(r.next_cycle_at) : undefined}
          />
        </>
      )}
      <NextAnalysis sched={sched} pending={schedPending} now={now} />
      <StatCard
        label="Auto-execution"
        icon={sys.auto_execution ? <LockOpen {...ICON} /> : <Lock {...ICON} />}
        value={sys.auto_execution ? 'ON' : 'OFF'}
        caption={sys.auto_execution ? undefined : 'Locked · Orbit never places an order'}
        title={sys.auto_execution ? undefined : 'Orbit suggests trades and logs what you decide. Auto-execution stays off until the system has earned trust.'}
      />
    </StatGrid>
  )
}

function NextAnalysis({ sched, pending, now }: { sched: ScheduleView | undefined; pending: boolean; now: number }) {
  const common = { label: 'Next analysis', icon: <CalendarClock {...ICON} />, title: "When the runner's daily analysis run is next due. You can also start one yourself under Analysis runs." }
  if (!sched) return <StatCard {...common} value="—" tone="dim" caption={pending ? 'Loading the schedule…' : 'Schedule unavailable'} />
  if (!sched.enabled) return <StatCard {...common} value="OFF" tone="dim" caption="Scheduled runs are off in settings" />
  if (!sched.runner_running) return <StatCard {...common} value="—" tone="dim" caption="Runner not running, so nothing is scheduled" />
  if (!sched.next_at) return <StatCard {...common} value="—" caption={`Daily at ${sched.daily_at_utc} UTC`} />
  return <StatCard {...common} value={until(sched.next_at, now)} caption={`${stamp(sched.next_at)} · daily at ${sched.daily_at_utc} UTC`} />
}

function Card({ area, icon, title, note, aside, children }: { area: string; icon: ReactNode; title: string; note?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className={`sys-card sys-card-${area}`}>
      <header className="sys-card-h">
        <span className="sys-card-ico">{icon}</span>
        <div className="sys-card-t">
          <h3>{title}</h3>
          {note && <p>{note}</p>}
        </div>
        {aside && <div className="sys-card-aside">{aside}</div>}
      </header>
      {children}
    </section>
  )
}

function RunHistory() {
  const { data } = useRuns()
  if (!data?.length) return null
  return (
    <>
      <div className="sys-sub">
        Recent runs <span>· hover a row for its step or error</span>
      </div>
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
                  <td className="l">{stamp(r.created_at)}</td>
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
    </>
  )
}
