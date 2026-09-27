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
  other_planet?: string | null
  event_type: string
  from_state?: string
  to_state: string
  backward?: boolean
  reentry?: boolean
  label?: string
}

/** Vedic graha names (src/orbit/vedic/zodiac.py SHORT), and 3-letter forms for chart markers. */
const GRAHA: Record<string, string> = {
  SUN: 'Surya', MOON: 'Chandra', MARS: 'Mangal', MERCURY: 'Budh', JUPITER: 'Guru', VENUS: 'Shukra', SATURN: 'Shani', RAHU: 'Rahu', KETU: 'Ketu',
}
const GRAHA_ABBR: Record<string, string> = {
  SUN: 'SUR', MOON: 'CHA', MARS: 'MAN', MERCURY: 'BUD', JUPITER: 'GUR', VENUS: 'SHU', SATURN: 'SHA', RAHU: 'RAH', KETU: 'KET',
}

export const grahaName = (p: string) => GRAHA[p] ?? p
export const planetAbbr = (p: string) => GRAHA_ABBR[p] ?? p

/** The backend's own label ("Shani (Saturn) enters Meena (Pisces)"), or a compact form for chart markers ("SHA→Meena"). */
export function transitLabel(e: TransitLike, short = false): string {
  if (!short && e.label) return e.label
  const a = planetAbbr(e.planet)
  const b = e.other_planet ? planetAbbr(e.other_planet) : ''
  const rashi = e.to_state.split(' (')[0]
  switch (e.event_type) {
    case 'INGRESS':
    case 'NAKSHATRA_INGRESS':
      return `${a}→${rashi}${e.backward ? ' (back)' : e.reentry ? ' (re)' : ''}`
    case 'STATION_RETROGRADE':
      return `${a} VAKRI`
    case 'STATION_DIRECT':
      return `${a} MARGI`
    case 'YUTI':
      return `${a}+${b}`
    case 'DRISHTI':
      return `${a}>${b} ${e.to_state}`
    case 'COMBUSTION':
      return `${a} ASTA`
    case 'GRAHA_YUDDHA':
      return `${a}×${b} YUDDHA`
    case 'SOLAR_ECLIPSE':
      return 'SURYA GRAHAN'
    case 'LUNAR_ECLIPSE':
      return 'CHANDRA GRAHAN'
    case 'AMAVASYA':
    case 'PURNIMA':
    case 'YOGA':
    case 'CLUSTER':
      return e.to_state ? `${e.event_type === 'YOGA' || e.event_type === 'CLUSTER' ? '' : e.event_type + ' '}${e.to_state}`.trim() : e.event_type
    default:
      return e.label ?? `${a} ${e.event_type}`
  }
}

/** A plain-words name for an event type, for tables. */
export const EVENT_KIND: Record<string, string> = {
  INGRESS: 'rashi ingress',
  NAKSHATRA_INGRESS: 'nakshatra',
  STATION_RETROGRADE: 'vakri',
  STATION_DIRECT: 'margi',
  YUTI: 'yuti',
  DRISHTI: 'drishti',
  COMBUSTION: 'asta',
  GRAHA_YUDDHA: 'yuddha',
  AMAVASYA: 'amavasya',
  PURNIMA: 'purnima',
  SOLAR_ECLIPSE: 'grahan',
  LUNAR_ECLIPSE: 'grahan',
  YOGA: 'yoga',
  CLUSTER: 'cluster',
}
