import { useEffect, useState } from 'react'
import { useComponents, useDecide, useSuggestions } from '../api/hooks'
import type { Decision, SuggestionView } from '../api/types'
import { Empty, NotBuilt, QueryState } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { parsePrice, validateLevels } from '../lib/decision'
import { ago, num, price, signed } from '../lib/format'
import { useTerminal } from '../state/store'

const ACTIONS: { decision: Decision; key: string; label: string; cls: string }[] = [
  { decision: 'TAKEN', key: 'T', label: 'TAKE', cls: 'take' },
  { decision: 'SKIPPED', key: 'S', label: 'SKIP', cls: 'skip' },
  { decision: 'MODIFIED', key: 'M', label: 'MODIFY', cls: 'mod' },
]

export function SuggestionsPanel({ hidden }: { hidden: boolean }) {
  const { components, error: sysError, isPending: sysPending } = useComponents()
  const built = !!components?.strategy
  const { data, isError, error } = useSuggestions(built)
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
      hidden={hidden}
      meta={
        <>
          <span>
            <span className="hi">{list.length}</span> PENDING
          </span>
          <span className="dim">J/K · T S M</span>
        </>
      }
    >
      {!components ? (
        <QueryState isPending={sysPending} error={sysError} what="system status" />
      ) : !built ? (
        <NotBuilt layer="STRATEGY">
          <span>This backend doesn't report a strategy layer. Update it to the latest code.</span>
        </NotBuilt>
      ) : isError ? (
        <QueryState isPending={false} error={error} what="suggestions" />
      ) : !current ? (
        <Empty title="QUEUE CLEAR">
          <span>No suggestions are waiting. The runner checks for a new RSI divergence on every completed daily bar.</span>
          <span className="dim">A suggestion expires if it isn't decided within 3 bars; it is still followed to its outcome.</span>
          <span className="dim">Every decision is logged in JRNL (F5).</span>
        </Empty>
      ) : (
        <div className="sugg">
          <div className="slist">
            {list.map((s, k) => (
              <button key={s.id} className={`srow ${s === current ? 'on' : ''}`} onClick={() => select(k)}>
                <span className="caret">▸</span>
                <span className="a">{ASSET_META[s.suggestion.asset].label}</span>
                <span className={`dir ${s.suggestion.direction.toLowerCase()}`}>{s.suggestion.direction}</span>
                <span className="confbar">
                  <span className="track">
                    <span className="fill" style={{ width: `${s.suggestion.confidence * 100}%` }} />
                  </span>
                  <span>{s.suggestion.confidence.toFixed(2)}</span>
                </span>
                <span className="rr">R:R {s.risk_reward.toFixed(1)}</span>
                <span className="age">{ago(s.created_at)}</span>
              </button>
            ))}
          </div>
          <Detail key={current.id} view={current} drawer={drawer} setDrawer={setDrawer} />
        </div>
      )}
    </Panel>
  )
}

function Detail({ view, drawer, setDrawer }: { view: SuggestionView; drawer: Decision | null; setDrawer: (d: Decision | null) => void }) {
  const s = view.suggestion
  const meta = ASSET_META[s.asset]
  const last = useTerminal((st) => st.prices[s.asset]) ?? s.entry_price
  const sd = s.direction === 'LONG' ? 1 : -1
  const risk = (Math.abs(s.entry_price - s.stop_loss) / s.entry_price) * 100
  const against = s.signals.filter((g) => g.direction !== s.direction).length
  const rungs: [string, number, string][] = (
    [
      ['TARGET', s.take_profit, 'tp'],
      ['ENTRY', s.entry_price, 'en'],
      ['LAST', last, 'lx'],
      ['STOP', s.stop_loss, 'sl'],
    ] as [string, number, string][]
  ).sort((x, y) => sd * (y[1] - x[1]))

  return (
    <div className="sdetail">
      <div className="shead">
        <span className={`big ${sd > 0 ? 'up' : 'down'}`}>
          {s.direction} {meta.label}
        </span>
        <span className="sub">
          {meta.pair} · 1D · suggested {ago(view.created_at)} ago · id {view.id}
        </span>
      </div>
      <div className="facts">
        <div>
          <span className="lbl">Confidence</span>
          <span className="v hi">{s.confidence.toFixed(2)}</span>
        </div>
        <div>
          <span className="lbl">Reward : risk</span>
          <span className="v">{view.risk_reward.toFixed(2)}</span>
        </div>
        <div>
          <span className="lbl">Risk to stop</span>
          <span className="v down">{num(risk)}%</span>
        </div>
        <div>
          <span className="lbl">Signals</span>
          <span className="v">
            {s.signals.length}
            {against > 0 && <span className="warn"> · {against} against</span>}
          </span>
        </div>
      </div>
      <div className="ladder">
        {rungs.map(([label, v, cls]) => (
          <div key={label} className={`rung ${cls}`}>
            <span className="lbl">{label}</span>
            <span className="bar" />
            <span>{price(s.asset, v)}</span>
            <span className="pct">{cls === 'lx' ? '' : `${signed((v / last - 1) * 100)}%`}</span>
          </div>
        ))}
      </div>
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
                <td className={g.direction === 'LONG' ? 'up' : 'down'}>{g.direction}</td>
                <td>
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
      {drawer ? (
        <DecisionForm view={view} decision={drawer} onCancel={() => setDrawer(null)} />
      ) : (
        <div className="actions">
          {ACTIONS.map((a) => (
            <button key={a.decision} className={`act ${a.cls}`} onClick={() => setDrawer(a.decision)}>
              <kbd>{a.key}</kbd>
              {a.label}
            </button>
          ))}
        </div>
      )}
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
        if (e.key === 'Escape') onCancel()
      }}
    >
      <span className="dt">
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
          <kbd>CTRL ↵</kbd>
          {decide.isPending ? 'LOGGING…' : `LOG ${decision}`}
        </button>
        <button type="button" className="act skip" onClick={onCancel}>
          <kbd>ESC</kbd>CANCEL
        </button>
        <span className="hint">Auto-execution is OFF. Logging does not place an order.</span>
      </div>
    </form>
  )
}
