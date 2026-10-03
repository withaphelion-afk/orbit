import { KeyRound } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CODE_REPO, DATA_REPO, STATIC } from '../api'
import { hasToken, onTokenChange, setToken } from '../api/static'

/**
 * The cloud build reads your private data with a GitHub token kept only in this browser. Until one is saved,
 * this screen asks for it in the page itself (browser pop-ups are blocked on many phones and installed apps).
 * On the server build it renders the app straight away.
 */
export function TokenGate({ children }: { children: ReactNode }) {
  const [ok, setOk] = useState(() => !STATIC || hasToken())
  const [value, setValue] = useState('')
  const qc = useQueryClient()
  useEffect(() => (STATIC ? onTokenChange(() => setOk(hasToken())) : undefined), [])
  if (ok) return <>{children}</>

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!value.trim()) return
    setToken(value)
    qc.invalidateQueries()
  }
  return (
    <div className="gate">
      <form className="gate-card" onSubmit={submit}>
        <span className="gate-ico">
          <KeyRound size={22} strokeWidth={1.75} />
        </span>
        <h1>Connect Orbit</h1>
        <p>
          Orbit reads your data from <b className="repo">{DATA_REPO}</b> and acts through <b className="repo">{CODE_REPO}</b>. Paste a GitHub fine-grained token with{' '}
          <b>Contents: Read</b> on the data repo and <b>Actions: Read and write</b> on the code repo. It stays in this browser only; each device needs its own.
        </p>
        <input
          type="password"
          autoComplete="off"
          autoFocus
          placeholder="github_pat_…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="GitHub token"
        />
        <button type="submit" className="act run" disabled={!value.trim()}>
          Connect
        </button>
      </form>
    </div>
  )
}
