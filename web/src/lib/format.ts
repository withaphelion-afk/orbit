import type { Asset } from '../api/types'
import { ASSET_META } from '../config'

const formatters = new Map<number, Intl.NumberFormat>()

export function num(v: number, dp = 2): string {
  let f = formatters.get(dp)
  if (!f) {
    f = new Intl.NumberFormat('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
    formatters.set(dp, f)
  }
  return f.format(v)
}

export const price = (asset: Asset, v: number) => num(v, ASSET_META[asset].dp)

/** Signed number with a real minus sign, e.g. "+1.20" / "−0.40". */
export function signed(v: number, dp = 2): string {
  const s = v > 0 ? '+' : v < 0 ? '−' : ''
  return s + num(Math.abs(v), dp)
}

export const tone = (v: number) => (v > 0 ? 'up' : v < 0 ? 'down' : 'mid')

export function day(t: string | number): string {
  return new Date(t).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' }).toUpperCase()
}

export function ago(t: string | number, now = Date.now()): string {
  const m = Math.max(0, Math.round((now - new Date(t).getTime()) / 60000))
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

export const hhmm = (t: string | number) => new Date(t).toISOString().slice(11, 16) + 'Z'
