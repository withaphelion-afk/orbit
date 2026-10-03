import { useQueryClient } from '@tanstack/react-query'
import { LogIn } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { STATIC } from '../api'
import { checkSession, login, onAuthChange } from '../api/static'

/** The cloud build's login. On the server build (a PC running Orbit) it renders the app straight away. */
export function LoginGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'checking' | 'in' | 'out'>(STATIC ? 'checking' : 'in')
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()

  useEffect(() => {
    if (!STATIC) return
    const recheck = () => checkSession().then((ok) => setState(ok ? 'in' : 'out'))
    recheck()
    return onAuthChange(recheck)
  }, [])

  if (state === 'in') return <>{children}</>
  if (state === 'checking') return <div className="gate" />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(user.trim(), pass)
      qc.invalidateQueries()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="gate">
      <form className="gate-card" onSubmit={submit}>
        <span className="gate-ico">
          <LogIn size={22} strokeWidth={1.75} />
        </span>
        <h1>Log in to Orbit</h1>
        <input autoFocus autoComplete="username" placeholder="Username" value={user} onChange={(e) => setUser(e.target.value)} aria-label="Username" />
        <input type="password" autoComplete="current-password" placeholder="Password" value={pass} onChange={(e) => setPass(e.target.value)} aria-label="Password" />
        {error && <p className="gate-err">{error}</p>}
        <button type="submit" className="act run" disabled={busy || !user.trim() || !pass}>
          {busy ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </div>
  )
}
