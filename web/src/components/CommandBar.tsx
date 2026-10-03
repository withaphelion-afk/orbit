import { useState } from 'react'
import { STATIC } from '../api'
import { useSystem } from '../api/hooks'
import type { Asset } from '../api/types'
import { ASSET_META } from '../config'
import { COMMAND_INPUT_ID } from '../hooks/useTerminalKeys'
import { useNow } from '../hooks/useLiveFeed'
import { findInstruments } from '../lib/commands'
import { useTerminal } from '../state/store'
import { Pill } from './bits'

function OrbitMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="13.2" cy="4.6" r="2" fill="currentColor" />
    </svg>
  )
}

/** Search an instrument by code, name or pair; picking one makes it the active asset. */
function InstrumentSearch() {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [hover, setHover] = useState(0)
  const asset = useTerminal((s) => s.asset)
  const setAsset = useTerminal((s) => s.setAsset)
  const matches = findInstruments(query)

  const pick = (a: Asset, input?: HTMLInputElement | null) => {
    setAsset(a)
    setQuery('')
    setOpen(false)
    input?.blur()
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setHover((h) => Math.min(h + 1, matches.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHover((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter' && matches[hover]) {
      pick(matches[hover], e.currentTarget)
    } else if (e.key === 'Escape') {
      setQuery('')
      setOpen(false)
      e.currentTarget.blur()
    }
  }

  return (
    <div className="search">
      <svg className="search-ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
      <input
        id={COMMAND_INPUT_ID}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setHover(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)} // let a click on an option land first
        onKeyDown={onKeyDown}
        autoComplete="off"
        spellCheck={false}
        placeholder={`Search instrument · ${ASSET_META[asset].label}`}
        aria-label="Search instrument"
        role="combobox"
        aria-expanded={open}
        aria-controls="instrument-list"
      />
      <kbd className="search-key">/</kbd>
      {open && (
        <ul className="search-list" id="instrument-list" role="listbox">
          {matches.length ? (
            matches.map((a, i) => (
              <li key={a} role="option" aria-selected={i === hover}>
                <button className={i === hover ? 'on' : ''} onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setHover(i)} onClick={() => pick(a)}>
                  <b>{ASSET_META[a].label}</b>
                  <span>{ASSET_META[a].name}</span>
                  <i>{ASSET_META[a].pair}</i>
                  {a === asset && <em>ACTIVE</em>}
                </button>
              </li>
            ))
          ) : (
            <li className="search-none">No instrument matches “{query}”.</li>
          )}
        </ul>
      )}
    </div>
  )
}

export function CommandBar() {
  const now = useNow(500)
  const lastTickAt = useTerminal((s) => s.lastTickAt)
  const connected = useTerminal((s) => s.feedConnected)
  const { data: sys, isError: apiDown, error: apiError } = useSystem()
  const age = lastTickAt ? Math.round((now - lastTickAt) / 1000) : null
  const runner = apiDown ? (STATIC ? 'NO DATA' : 'API DOWN') : sys ? sys.runner.state.replace('_', ' ') : '…'
  const d = new Date(now)

  return (
    <header className="topbar">
      <div className="brand">
        <OrbitMark />
        Orbit
      </div>
      <InstrumentSearch />
      <div className="status">
        <span className="chip">
          <i className={`dot ${runner === 'LIVE' ? '' : 'bad'}`} aria-hidden="true" />
          Runner <b>{runner}</b>
        </span>
        <span className="chip opt">
          Feed <b className={connected ? '' : 'down'}>{connected ? (age === null ? '—' : `${age}s`) : 'OFF'}</b>
        </span>
        <span className="chip opt">
          Strategy <b className={sys && !sys.strategy ? 'dim' : ''}>{sys ? (sys.strategy ?? 'NOT BUILT') : '—'}</b>
        </span>
        <span className="chip">
          Auto-exec <Pill tone="off">{sys?.auto_execution ? 'ON' : 'OFF'}</Pill>
        </span>
        {apiDown && (
          <Pill
            tone="drift"
            title={STATIC ? `Can't read Orbit's data: ${apiError instanceof Error ? apiError.message : 'no answer from GitHub'}` : "The Orbit API isn't answering. Start it with: python scripts/start_orbit.py"}
          >
            {STATIC ? 'NOT CONNECTED' : 'API OFFLINE'}
          </Pill>
        )}
        <span className="chip clock">
          UTC <b>{d.toISOString().slice(11, 19)}</b>
        </span>
        <span className="chip clock opt">
          Local <b>{d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</b>
        </span>
      </div>
    </header>
  )
}
