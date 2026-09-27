import { useEffect } from 'react'
import { ASSETS } from '../config'
import { FUNCTIONS } from '../lib/commands'
import { useTerminal } from '../state/store'

export const COMMAND_INPUT_ID = 'cmd'

const isField = (el: Element | null) => !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || (el as HTMLElement).isContentEditable)

/**
 * Terminal-wide keys: F1-F8 switch function, Ctrl/Cmd+K opens the palette,
 * "/" focuses the command line, 1-4 switch asset, Esc steps back to MON.
 * Panel-specific keys (J/K/T/S/M in SUGG) live in their panels.
 */
export function useTerminalKeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = useTerminal.getState()
      const fk = /^F([1-8])$/.exec(e.key)
      if (fk) {
        e.preventDefault()
        t.setView(FUNCTIONS[Number(fk[1]) - 1].code)
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        t.setPaletteOpen(!t.paletteOpen)
        return
      }
      if (t.paletteOpen || e.defaultPrevented) return
      const active = document.activeElement
      if (e.key === 'Escape') {
        if (isField(active)) (active as HTMLElement).blur()
        else if (t.view !== 'MON') t.setView('MON')
        return
      }
      if (isField(active) || e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === '/') {
        e.preventDefault()
        document.getElementById(COMMAND_INPUT_ID)?.focus()
        return
      }
      if (/^[1-4]$/.test(e.key)) {
        t.setAsset(ASSETS[Number(e.key) - 1])
        return
      }
      // Any other letter starts typing a command, Bloomberg-style.
      if (/^[a-z]$/i.test(e.key)) document.getElementById(COMMAND_INPUT_ID)?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
