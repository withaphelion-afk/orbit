import { useRef, useState } from 'react'
import { useSystem } from '../api/hooks'
import { COMMAND_INPUT_ID } from '../hooks/useTerminalKeys'
import { useNow } from '../hooks/useLiveFeed'
import { complete } from '../lib/commands'
import { runCommand, useTerminal } from '../state/store'
import { Pill } from './bits'

function OrbitMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="13.2" cy="4.6" r="2" fill="currentColor" />
    </svg>
  )
}

export function CommandBar() {
  const [value, setValue] = useState('')
  const history = useRef<string[]>([])
  const cursor = useRef(-1)
  const now = useNow(500)
  const lastTickAt = useTerminal((s) => s.lastTickAt)
  const connected = useTerminal((s) => s.feedConnected)
  const { data: sys, isError: apiDown } = useSystem()
  const ghost = complete(value)

  const submit = () => {
    if (runCommand(value)) history.current.unshift(value.toUpperCase())
    cursor.current = -1
    setValue('')
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') submit()
    else if (e.key === 'Tab' && ghost) {
      e.preventDefault()
      setValue(ghost)
    } else if (e.key === 'ArrowUp' && history.current.length) {
      e.preventDefault()
      cursor.current = Math.min(cursor.current + 1, history.current.length - 1)
      setValue(history.current[cursor.current])
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      cursor.current = Math.max(cursor.current - 1, -1)
      setValue(cursor.current < 0 ? '' : history.current[cursor.current])
    } else if (e.key === 'Escape') {
      setValue('')
      e.currentTarget.blur()
    }
  }

  const age = lastTickAt ? Math.round((now - lastTickAt) / 1000) : null
  const runner = apiDown ? 'API DOWN' : sys ? sys.runner.state.replace('_', ' ') : '…'
  const d = new Date(now)

  return (
    <header className="cmdbar">
      <div className="brand">
        <OrbitMark />
        ORBIT
      </div>
      <div className="cmd">
        <span className="prompt">&gt;</span>
        <div className="cmd-field">
          <span className="ghost" aria-hidden="true">
            {ghost ?? ''}
          </span>
          <input
            id={COMMAND_INPUT_ID}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            autoComplete="off"
            spellCheck={false}
            placeholder="SOL GP  ·  SUGG  ·  HELP"
            aria-label="Command line"
          />
        </div>
        <button className="go" onClick={submit} title="Run command (Enter)">
          GO
        </button>
      </div>
      <div className="status">
        <span>
          <i className={`dot ${runner === 'LIVE' ? '' : 'bad'}`} aria-hidden="true" />
          RUNNER <b>{runner}</b>
        </span>
        <span className="opt">
          FEED <b className={connected ? '' : 'down'}>{connected ? (age === null ? '—' : `${age}s`) : 'OFF'}</b>
        </span>
        <span className="opt">
          STRATEGY <b className={sys && !sys.strategy ? 'dim' : ''}>{sys ? (sys.strategy ?? 'NOT BUILT') : '—'}</b>
        </span>
        <span>
          AUTO-EXEC <Pill tone="off">{sys?.auto_execution ? 'ON' : 'OFF'}</Pill>
        </span>
        {apiDown && (
          <span>
            <Pill tone="drift" title="The Orbit API isn't answering. Start it with: uv run python -m orbit.api">
              API OFFLINE
            </Pill>
          </span>
        )}
        <span>
          UTC <b>{d.toISOString().slice(11, 19)}</b>
        </span>
        <span className="opt">
          LOCAL <b>{d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</b>
        </span>
      </div>
    </header>
  )
}
