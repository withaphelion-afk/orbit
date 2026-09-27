import { create } from 'zustand'
import type { Asset } from '../api/types'
import { ASSETS, type TvInterval } from '../config'
import { parseCommand, type View } from '../lib/commands'

export type ChartMode = 'LIVE' | 'ORBIT'

interface Toast {
  id: number
  text: string
  error: boolean
}

interface TerminalState {
  view: View
  asset: Asset
  chartMode: ChartMode
  tvInterval: TvInterval
  prices: Partial<Record<Asset, number>>
  lastTickAt: number | null
  feedConnected: boolean
  paletteOpen: boolean
  toast: Toast | null

  setView: (v: View) => void
  setAsset: (a: Asset) => void
  setChartMode: (m: ChartMode) => void
  setTvInterval: (i: TvInterval) => void
  applyTick: (a: Asset, price: number) => void
  setFeedConnected: (ok: boolean) => void
  setPaletteOpen: (open: boolean) => void
  notify: (text: string, error?: boolean) => void
}

// Per-viewer conveniences only; the app works identically without storage.
const remember = (k: string, v?: string): string | null => {
  try {
    if (v === undefined) return localStorage.getItem(`orbit.${k}`)
    localStorage.setItem(`orbit.${k}`, v)
  } catch {
    // storage blocked: fall back to defaults
  }
  return null
}

const savedAsset = remember('asset') as Asset | null
const savedMode = remember('chartMode') as ChartMode | null
const savedInterval = remember('tvInterval') as TvInterval | null

export const useTerminal = create<TerminalState>((set) => ({
  view: 'MON',
  asset: savedAsset && ASSETS.includes(savedAsset) ? savedAsset : 'SOL',
  chartMode: savedMode === 'ORBIT' ? 'ORBIT' : 'LIVE',
  tvInterval: savedInterval ?? 'D',
  prices: {},
  lastTickAt: null,
  feedConnected: false,
  paletteOpen: false,
  toast: null,

  setView: (view) => set({ view }),
  setAsset: (asset) => {
    remember('asset', asset)
    set({ asset })
  },
  setChartMode: (chartMode) => {
    remember('chartMode', chartMode)
    set({ chartMode })
  },
  setTvInterval: (tvInterval) => {
    remember('tvInterval', tvInterval)
    set({ tvInterval })
  },
  applyTick: (a, price) => set((s) => ({ prices: { ...s.prices, [a]: price }, lastTickAt: Date.now() })),
  setFeedConnected: (feedConnected) => set({ feedConnected }),
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  notify: (text, error = false) => set({ toast: { id: Date.now(), text, error } }),
}))

/** Runs a command-line string against the terminal. Shared by the command bar and palette. */
export function runCommand(input: string): boolean {
  const parsed = parseCommand(input)
  if (!parsed) return false
  const t = useTerminal.getState()
  if ('error' in parsed) {
    t.notify(parsed.error, true)
    return false
  }
  if (parsed.asset) t.setAsset(parsed.asset)
  if (parsed.view) t.setView(parsed.view)
  else if (parsed.asset && t.view !== 'MON' && t.view !== 'GP') t.setView('GP')
  t.notify(`> ${[parsed.asset, parsed.view].filter(Boolean).join(' ')} <GO>`)
  return true
}
