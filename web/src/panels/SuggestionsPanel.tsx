import { useEffect, useState } from 'react'
import { ChartLine, Check, ChevronRight, Gauge, Hourglass, Inbox, Pencil, Scale, SkipForward, TrendingDown, TrendingUp, X, type LucideIcon } from 'lucide-react'
import { useComponents, useDecide, useSignals, useSuggestions } from '../api/hooks'
import type { Asset, Decision, Signal, SuggestionView, TradeSuggestion } from '../api/types'
import { Empty, NotBuilt, QueryState, StatCard, StatGrid } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSETS, ASSET_META } from '../config'
import { parsePrice, validateLevels } from '../lib/decision'
import { ago, daysFrom, num, price, signed } from '../lib/format'
import { useTerminal } from '../state/store'

const ACTIONS: { decision: Decision; key: string; label: string; cls: string; Icon: LucideIcon }[] = [
  { decision: 'TAKEN', key: 'T', label: 'TAKE', cls: 'take', Icon: Check },
  { decision: 'SKIPPED', key: 'S', label: 'SKIP', cls: 'skip', Icon: SkipForward },
  { decision: 'MODIFIED', key: 'M', label: 'MODIFY', cls: 'mod', Icon: Pencil },
]

/** Daily bars an undecided suggestion waits before it expires (backend: SUGGESTION_EXPIRY_BARS). */
const EXPIRY_BARS = 3
const ICON = { size: 18, strokeWidth: 1.75 } as const
const SMALL = { size: 15, strokeWidth: 1.75 } as const

const riskPct = (s: TradeSuggestion) => (Math.abs(s.entry_price - s.stop_loss) / s.entry_price) * 100

/** "02 Sep 2026" (UTC). */
function fullDate(t: string) {
  const d = new Date(t)
  return `${String(d.getUTCDate()).padStart(2, '0')} ${d.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' })} ${d.getUTCFullYear()}`
}

export function SuggestionsPanel({ hidden }: { hidden: boolean }) {
  const { components, error: sysError, isPending: sysPending } = useComponents()
  const built = !!components?.strategy
  const { data, isError, error, isPending } = useSuggestions(built)
  const list = data ?? []
  const [sel, setSel] = useState(0)
  const [drawer, setDrawer] = useState<Decision | null>(null)
  const setAsset = useTerminal((s) => s.setAsset)
  const current = list[Math.min(sel, list.length - 1)]

  const select = (k: number) => {
    setSel(k)
    setDrawer(null)
    if (list[k]) setAsset(list[k].suggestion.asset)
  }

  // J/K move, T/S/M open the decision form. Only while this panel is showing.
  useEffect(() => {
    if (hidden) return
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return
      if (e.ctrlKey || e.metaKey || e.altKey || !list.length || useTerminal.getState().paletteOpen) return
      const k = e.key.toLowerCase()
      if (k === 'j' || k === 'k') {
        e.preventDefault()
        select((sel + (k === 'j' ? 1 : -1) + list.length) % list.length)
      } else if (k === 't' || k === 's' || k === 'm') {
        e.preventDefault()
        setDrawer(ACTIONS.find((a) => a.key.toLowerCase() === k)!.decision)
      } else if (e.key === 'Escape' && drawer) {
        e.preventDefault()
        setDrawer(null)
      }
    }
    // Capture phase so these win over the terminal's "letters focus the command line".
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  return (
    <Panel
      code="SUGG"
      title="Suggestions awaiting decision"
      description="RSI divergence trade ideas waiting for you to take, skip or modify; decisions are logged to the journal and never place an order."
      hidden={hidden}
    >
      {!components ? (
        <QueryState isPending={sysPending} error={sysError} what="system status" />
      ) : !built ? (
        <NotBuilt layer="STRATEGY">
          <span>This backend doesn't report a strategy layer. Update it to the latest code.</span>
        </NotBuilt>
      ) : isError ? (
        <QueryState isPending={false} error={error} what="suggestions" />
      ) : !data ? (
        <QueryState isPending={isPending} error={null} what="suggestions" />
      ) : (
        <div className="sg">
          <SuggestionStats list={list} current={current} />
          {!current ? (
            <QueueClear />
          ) : (
            <div className="sugg">
              <div className="slist">
                <div className="slist-head" aria-hidden="true">
                  <span>Side</span>
                  <span>Asset</span>
                  <span>TF</span>
                  <span>Confidence</span>
                  <span className="r">R:R</span>
                  <span className="r">Age</span>
                  <span />
                </div>
                <div className="slist-rows">
                  {list.map((s, k) => {
                    const on = s === current
                    const conf = s.suggestion.confidence.toFixed(2)
                    return (
                      <button key={s.id} type="button" className={`srow ${on ? 'on' : ''}`} aria-current={on ? 'true' : undefined} onClick={() => select(k)}>
                        <span className={`dir ${s.suggestion.direction.toLowerCase()}`}>{s.suggestion.direction}</span>
                        <span className="a">{ASSET_META[s.suggestion.asset].label}</span>
                        <span className="tf" title="The bars it lives on: expiry and outcome count bars of this timeframe">{(s.timeframe ?? '1d').toUpperCase()}</span>
                        <span className="confbar" title={`Confidence ${conf}: the estimated chance this trade ends with a win`}>
                          <span className="track">
                            <span className="fill" style={{ width: `${s.suggestion.confidence * 100}%` }} />
                          </span>
                          <span>{conf}</span>
                        </span>
                        <span className="rr" title="Reward : risk">
                          {s.risk_reward.toFixed(1)}
                        </span>
                        <span className="age" title={`Suggested ${ago(s.created_at)} ago`}>
                          {ago(s.created_at)}
                        </span>
                        <ChevronRight className="chev" size={16} strokeWidth={1.75} aria-hidden="true" />
                      </button>
                    )
                  })}
                </div>
                <div className="slist-foot">
                  <kbd>J</kbd>
                  <kbd>K</kbd>
                  <span>next / previous suggestion</span>
                </div>
              </div>
              <Detail key={current.id} view={current} drawer={drawer} setDrawer={setDrawer} />
            </div>
          )}
        </div>
      )}
    </Panel>
  )
}

function SuggestionStats({ list, current }: { list: SuggestionView[]; current?: SuggestionView }) {
  const longs = list.filter((v) => v.suggestion.direction === 'LONG').length
  const s = current?.suggestion
  return (
    <StatGrid>
      <StatCard
        label="Pending"
        value={list.length}
        caption={list.length ? `${longs} long · ${list.length - longs} short` : 'Queue clear'}
        icon={<Inbox {...ICON} />}
        title="Suggestions waiting for your decision. The queue refreshes every 30 seconds."
      />
      <StatCard
        label="Confidence basis"
        value="P(win)"
        caption="Chance of a win, learned from past outcomes"
        icon={<Gauge {...ICON} />}
        title="Each suggestion's confidence is the estimated chance the trade ends with a win, from the feedback loop (DRIFT) retrained on backtest trades and finished live suggestions. Until that model beats the plain win rate out of sample, every suggestion gets the plain win rate."
      />
      <StatCard
        label="Expiry"
        value={`${EXPIRY_BARS} bars`}
        caption="Undecided ones go to JRNL as skipped"
        icon={<Hourglass {...ICON} />}
        title={`A suggestion expires if it isn't decided within ${EXPIRY_BARS} daily bars; it is still followed to its outcome.`}
      />
      <StatCard
        label="Reward : risk"
        value={current ? current.risk_reward.toFixed(2) : '—'}
        tone={current ? undefined : 'dim'}
        caption={s ? `${s.direction} ${ASSET_META[s.asset].label} · ${num(riskPct(s))}% risk to stop` : 'Nothing selected'}
        icon={<Scale {...ICON} />}
        title="For the selected suggestion: the distance from entry to target divided by the distance from entry to stop."
      />
    </StatGrid>
  )
}

function QueueClear() {
  return (
    <div className="sg-clear">
      <section className="sg-card sg-why">
        <span className="sg-ico">
          <Inbox {...ICON} />
        </span>
        <Empty title="QUEUE CLEAR">
          <span>
            No suggestions are waiting. A suggestion only appears when an RSI divergence confirms on the latest completed daily bar; the runner checks for one on every
            completed daily bar.
          </span>
          <span className="dim">A suggestion expires if it isn't decided within {EXPIRY_BARS} bars; it is still followed to its outcome.</span>
          <span className="dim">Every decision is logged in JRNL (F5).</span>
        </Empty>
      </section>
      <section className="sg-card">
        <header className="sg-card-head">
          <span className="sg-card-title">Latest RSI divergence per asset</span>
          <span className="sg-card-sub">The most recent divergence in each asset's stored history, dated to the bar it confirmed on. Hover a date for the reason.</span>
        </header>
        <ul className="sg-divs">
          {ASSETS.map((a) => (
            <LatestDivergence key={a} asset={a} />
          ))}
        </ul>
      </section>
    </div>
  )
}

function LatestDivergence({ asset }: { asset: Asset }) {
  const { data, isPending, error } = useSignals(asset)
  const setAsset = useTerminal((s) => s.setAsset)
  const setChartMode = useTerminal((s) => s.setChartMode)
  const setView = useTerminal((s) => s.setView)
  const meta = ASSET_META[asset]
  let last: Signal | null = null
  for (const g of data ?? []) {
    if (g.name !== 'rsi_divergence') continue
    if (!last || new Date(g.timestamp).getTime() > new Date(last.timestamp).getTime()) last = g
  }

  const openChart = () => {
    setAsset(asset)
    setChartMode('ORBIT')
    setView('GP')
  }

  return (
    <li className="sg-div">
      <span className="sg-div-asset">
        <b>{meta.label}</b>
        <span>{meta.name}</span>
      </span>
      <span className="sg-div-sig">
        {error ? (
          <span className="down" title={error instanceof Error ? error.message : String(error)}>
            Couldn't load signals
          </span>
        ) : isPending ? (
          <span className="dim">Loading…</span>
        ) : last ? (
          <>
            <span className={`dir ${last.direction.toLowerCase()}`}>{last.direction}</span>
            <span className="when" title={last.reason}>
              {fullDate(last.timestamp)}
              <i>{daysFrom(last.timestamp)}</i>
            </span>
          </>
        ) : (
          <span className="dim">None in the stored history</span>
        )}
      </span>
      <button type="button" className="act skip sg-open" onClick={openChart} title={`Open ${meta.label} on Orbit's daily chart, where RSI divergences are marked`}>
        <ChartLine {...SMALL} aria-hidden="true" />
        CHART
      </button>
    </li>
  )
}

function Detail({ view, drawer, setDrawer }: { view: SuggestionView; drawer: Decision | null; setDrawer: (d: Decision | null) => void }) {
  const s = view.suggestion
  const meta = ASSET_META[s.asset]
  const last = useTerminal((st) => st.prices[s.asset]) ?? s.entry_price
  const sd = s.direction === 'LONG' ? 1 : -1
  const risk = riskPct(s)
  const against = s.signals.filter((g) => g.direction !== s.direction).length
  const rungs: [string, number, string][] = (
    [
      ['TARGET', s.take_profit, 'tp'],
      ['ENTRY', s.entry_price, 'en'],
      ['LAST', last, 'lx'],
      ['STOP', s.stop_loss, 'sl'],
    ] as [string, number, string][]
  ).sort((x, y) => sd * (y[1] - x[1]))
  const DirIcon = sd > 0 ? TrendingUp : TrendingDown

  return (
    <div className="sdetail">
      <header className="shead">
        <span className={`big ${sd > 0 ? 'up' : 'down'}`}>
          <DirIcon {...ICON} aria-hidden="true" />
          {s.direction} {meta.label}
        </span>
        <span className="sub">
          {meta.pair} · 1D · suggested {ago(view.created_at)} ago · id {view.id}
        </span>
      </header>
      <div className="sbody">
        <div className="facts">
          <div title="The estimated chance this trade ends with a win (P(win))">
            <span className="lbl">Confidence</span>
            <span className="v hi">{s.confidence.toFixed(2)}</span>
          </div>
          <div title="How far the stop is from the entry price">
            <span className="lbl">Risk to stop</span>
            <span className="v down">{num(risk)}%</span>
          </div>
          <div title="Signals behind this suggestion; ones pointing the other way are counted as against">
            <span className="lbl">Signals</span>
            <span className="v">
              {s.signals.length}
              {against > 0 && <span className="warn"> · {against} against</span>}
            </span>
          </div>
        </div>
        <div className="sgrid">
          <section className="sbox">
            <div className="sbox-head">
              <span className="lbl">Levels</span>
              <span className="lbl" title="Each level's distance from the last price">
                vs last
              </span>
            </div>
            <div className="ladder">
              {rungs.map(([label, v, cls]) => (
                <div key={label} className={`rung ${cls}`} title={cls === 'lx' ? 'Latest price from the live feed (the entry price until a tick arrives)' : undefined}>
                  <span className="lbl">{label}</span>
                  <span className="bar" />
                  <span>{price(s.asset, v)}</span>
                  <span className="pct">{cls === 'lx' ? '' : `${signed((v / last - 1) * 100)}%`}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="sbox">
            <div className="sbox-head">
              <span className="lbl">Signals</span>
            </div>
            <div className="sigwrap">
              <table className="sigs">
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>Dir</th>
                    <th>Strength</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {s.signals.map((g) => {
                    const isAgainst = g.direction !== s.direction
                    return (
                      <tr key={g.name} className={isAgainst ? 'against' : ''}>
                        <td className="nm">{g.name}</td>
                        <td className={`sd ${g.direction === 'LONG' ? 'up' : 'down'}`}>{g.direction}</td>
                        <td className="st">
                          {g.strength.toFixed(2)}
                          <div className="sbar">
                            <i style={{ width: `${g.strength * 100}%`, background: isAgainst ? 'var(--warn)' : g.name.startsWith('astro') ? 'var(--astro)' : 'var(--accent)' }} />
                          </div>
                        </td>
                        <td className="rs">{g.reason}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
      <footer className="sfoot">
        {drawer ? (
          <DecisionForm view={view} decision={drawer} onCancel={() => setDrawer(null)} />
        ) : (
          <div className="actions">
            {ACTIONS.map((a) => (
              <button key={a.decision} type="button" className={`act ${a.cls}`} onClick={() => setDrawer(a.decision)}>
                <a.Icon {...SMALL} aria-hidden="true" />
                {a.label}
                <kbd>{a.key}</kbd>
              </button>
            ))}
          </div>
        )}
      </footer>
    </div>
  )
}

function DecisionForm({ view, decision, onCancel }: { view: SuggestionView; decision: Decision; onCancel: () => void }) {
  const s = view.suggestion
  const dp = ASSET_META[s.asset].dp
  const [notes, setNotes] = useState('')
  const [levels, setLevels] = useState({ entry: s.entry_price.toFixed(dp), stop: s.stop_loss.toFixed(dp), target: s.take_profit.toFixed(dp) })
  const decide = useDecide()
  const notify = useTerminal((st) => st.notify)
  const action = ACTIONS.find((a) => a.decision === decision)!
  const label = ASSET_META[s.asset].label

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault()
    let extra = {}
    if (decision === 'MODIFIED') {
      const entry = parsePrice(levels.entry)
      const stop = parsePrice(levels.stop)
      const target = parsePrice(levels.target)
      const problem = validateLevels(s.direction, entry, stop, target)
      if (problem) return notify(problem, true)
      extra = { entry_price: entry, stop_loss: stop, take_profit: target }
    }
    decide.mutate(
      { id: view.id, req: { decision, notes: notes.trim(), ...extra } },
      {
        onSuccess: () => notify(`LOGGED · ${decision} ${label} ${s.direction} → JRNL`),
        onError: (err) => notify(`NOT LOGGED: ${String(err).toUpperCase()}`, true),
      },
    )
  }

  return (
    <form
      className="drawer"
      onSubmit={submit}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit()
        if (e.key === 'Escape') {
          e.preventDefault() // only close the form; the terminal's Esc would also leave SUGG
          onCancel()
        }
      }}
    >
      <span className="dt">
        <action.Icon {...SMALL} aria-hidden="true" />
        {action.label} {s.direction} {label} · LOG TO JOURNAL
      </span>
      {decision === 'MODIFIED' && (
        <div className="fields">
          {(['entry', 'stop', 'target'] as const).map((k, i) => (
            <label key={k}>
              <span className="lbl">{k}</span>
              <input id={`d-${k}`} inputMode="decimal" autoFocus={i === 0} value={levels[k]} onChange={(e) => setLevels({ ...levels, [k]: e.target.value })} />
            </label>
          ))}
        </div>
      )}
      <label>
        <span className="lbl">Note (optional, the feedback loop reads these)</span>
        <textarea
          id="d-notes"
          autoFocus={decision !== 'MODIFIED'}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={decision === 'SKIPPED' ? 'Why pass on it?' : "Anything the rules didn't capture?"}
        />
      </label>
      <div className="actions">
        <button type="submit" className={`act ${action.cls}`} disabled={decide.isPending}>
          <action.Icon {...SMALL} aria-hidden="true" />
          {decide.isPending ? 'LOGGING…' : `LOG ${decision}`}
          <kbd>CTRL ↵</kbd>
        </button>
        <button type="button" className="act skip" onClick={onCancel}>
          <X {...SMALL} aria-hidden="true" />
          CANCEL
          <kbd>ESC</kbd>
        </button>
        <span className="hint">Auto-execution is OFF. Logging does not place an order.</span>
      </div>
    </form>
  )
}
