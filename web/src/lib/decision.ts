import type { Direction } from '../api/types'

/**
 * Checks hand-edited levels for a MODIFIED decision. Returns a message to show,
 * or null when the levels make sense for the direction.
 */
export function validateLevels(direction: Direction, entry: number, stop: number, target: number): string | null {
  if (![entry, stop, target].every((v) => Number.isFinite(v) && v > 0)) {
    return 'ENTRY, STOP AND TARGET MUST BE POSITIVE NUMBERS'
  }
  const long = direction === 'LONG'
  const ok = long ? stop < entry && target > entry : stop > entry && target < entry
  if (!ok) {
    return long
      ? 'FOR A LONG, STOP MUST BE BELOW ENTRY AND TARGET ABOVE IT'
      : 'FOR A SHORT, STOP MUST BE ABOVE ENTRY AND TARGET BELOW IT'
  }
  return null
}

export const riskReward = (entry: number, stop: number, target: number) => Math.abs(target - entry) / Math.abs(entry - stop)

/** Parses "64,210.50" style input. */
export const parsePrice = (s: string) => parseFloat(s.replace(/,/g, ''))
