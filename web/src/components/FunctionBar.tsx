import { useComponents, useSuggestions, useSystem } from '../api/hooks'
import { useNow } from '../hooks/useLiveFeed'
import { FUNCTIONS, type View } from '../lib/commands'
import { useTerminal } from '../state/store'

/** Navigation order (F-keys keep their own order: F1 is Help). */
const NAV: View[] = ['MON', 'GP', 'SUGG', 'JRNL', 'DRIFT', 'ASTRO', 'SYS', 'HELP']
const BY_CODE = new Map(FUNCTIONS.map((f) => [f.code, f]))

/** The floating navigation at the bottom of every page, and the snackbar above it. */
export function FunctionBar() {
  const view = useTerminal((s) => s.view)
  const setView = useTerminal((s) => s.setView)
  const toast = useTerminal((s) => s.toast)
  const now = useNow(500)
  const visible = !!toast && now - toast.id < 5000 // toast.id is its creation time
  const { components } = useComponents()
  const pending = useSuggestions(!!components?.strategy).data?.length ?? 0
  const { data: sys } = useSystem()
  const runnerDown = !!sys && sys.runner.state !== 'LIVE'

  return (
    <>
      <div className={`snackbar ${visible ? 'show' : ''} ${toast?.error ? 'err' : ''}`} role="status" aria-live="polite">
        {visible ? toast?.text : ''}
      </div>
      <nav className="dock" aria-label="Pages">
        {NAV.map((code) => {
          const f = BY_CODE.get(code)!
          return (
            <button key={code} className={view === code ? 'on' : ''} onClick={() => setView(code)} title={`${f.desc} (${f.key})`} aria-current={view === code ? 'page' : undefined}>
              {f.label}
              {code === 'SUGG' && pending > 0 && <span className="badge">{pending}</span>}
              {code === 'SYS' && runnerDown && <span className="badge dot" aria-label="Runner not live" />}
            </button>
          )
        })}
      </nav>
    </>
  )
}
