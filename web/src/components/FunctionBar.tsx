import { useNow } from '../hooks/useLiveFeed'
import { FUNCTIONS } from '../lib/commands'
import { useTerminal } from '../state/store'

export function FunctionBar() {
  const view = useTerminal((s) => s.view)
  const setView = useTerminal((s) => s.setView)
  const toast = useTerminal((s) => s.toast)
  const now = useNow(500)
  const visible = !!toast && now - toast.id < 5000 // toast.id is its creation time

  return (
    <footer className="fkeys">
      {FUNCTIONS.map((f) => (
        <button key={f.code} className={`fk ${view === f.code ? 'on' : ''}`} onClick={() => setView(f.code)} title={f.desc}>
          <kbd>{f.key}</kbd>
          {f.code}
        </button>
      ))}
      <span className={`toast ${toast?.error ? 'err' : ''}`} role="status">
        {visible ? toast?.text : ''}
      </span>
      <span className="fk-hint">CTRL K PALETTE</span>
    </footer>
  )
}
