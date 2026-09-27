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

const DAY_MS = 86_400_000

/** "today", "in 3d", "5d ago" relative to the current UTC day. */
export function daysFrom(t: string | number, now = Date.now()): string {
  const today = now - (now % DAY_MS)
  const d = Math.round((new Date(t).getTime() - today) / DAY_MS)
  return d === 0 ? 'today' : d > 0 ? `in ${d}d` : `${-d}d ago`
}

export const pct = (v: number, dp = 0) => `${num(v * 100, dp)}%`

/** p/q values: 3 significant figures, "<0.001" at the floor. */
export function pval(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v < 0.001 ? '<0.001' : v.toFixed(3)
}

interface TransitLike {
  planet: string
  event_type: 'INGRESS' | 'STATION_RETROGRADE' | 'STATION_DIRECT'
  to_state: string
  backward?: boolean
  reentry?: boolean
}

const PLANET_ABBR: Record<string, string> = {
  SUN: 'SUN', MOON: 'MOON', MERCURY: 'MER', VENUS: 'VEN', MARS: 'MAR', JUPITER: 'JUP', SATURN: 'SAT', URANUS: 'URA', NEPTUNE: 'NEP', PLUTO: 'PLU',
}

export const planetAbbr = (p: string) => PLANET_ABBR[p] ?? p

/** "Mars → Aries", "Mercury Rx", "Mercury D". */
export function transitLabel(e: TransitLike, short = false): string {
  const name = short ? planetAbbr(e.planet) : e.planet[0] + e.planet.slice(1).toLowerCase()
  if (e.event_type === 'INGRESS') return `${name} → ${e.to_state}${e.backward ? ' (back)' : e.reentry ? ' (re-entry)' : ''}`
  return `${name} ${e.event_type === 'STATION_RETROGRADE' ? 'Rx' : 'D'}`
}
