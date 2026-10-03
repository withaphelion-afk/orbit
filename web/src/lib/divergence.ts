/**
 * RSI divergence detection: the one algorithm, in TypeScript.
 *
 * src/orbit/strategy/divergence.py is the same algorithm in Python (the runner trains, backtests and
 * suggests with it). Both must find exactly the same divergences: tests/fixtures/divergence_cases.json
 * holds shared cases both test suites check. Change both together.
 *
 *   RSI      Wilder's RSI(14) of the close
 *   swings   lower (higher) than the 2 bars before, no higher (lower) than the 2 after; strength = bars back it stays the extreme (max 100)
 *   pairs    two swings of a kind 5-60 bars apart where price and RSI disagree: regular or hidden, bullish (LONG) or bearish (SHORT)
 *   forming  the second swing is one of the last 2 bars and still the extreme so far (dashed, never alerted)
 */

export const RSI_PERIOD = 14
export const LEFT = 2
export const RIGHT = 2
export const MIN_GAP = 5
export const MAX_GAP = 60
export const MAX_STRENGTH = 100

export interface Candidate {
  kind: 'regular' | 'hidden'
  direction: 'LONG' | 'SHORT'
  i: number
  j: number
  confirm: number | null
  p1: number
  p2: number
  r1: number
  r2: number
  s1: number
  s2: number
}

/** Wilder's RSI; NaN for the first n bars. Same operations, in the same order, as the Python version. */
export function rsi(close: ArrayLike<number>, n = RSI_PERIOD): number[] {
  const out = new Array<number>(close.length).fill(NaN)
  if (close.length <= n) return out
  let gain = 0
  let loss = 0
  for (let k = 1; k <= n; k++) {
    const d = close[k] - close[k - 1]
    gain += d > 0 ? d : 0
    loss += d < 0 ? -d : 0
  }
  gain /= n
  loss /= n
  out[n] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss)
  for (let k = n + 1; k < close.length; k++) {
    const d = close[k] - close[k - 1]
    gain = (gain * (n - 1) + (d > 0 ? d : 0)) / n
    loss = (loss * (n - 1) + (d < 0 ? -d : 0)) / n
    out[k] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss)
  }
  return out
}

function isLow(low: ArrayLike<number>, k: number, right: number): boolean {
  if (k < LEFT) return false
  for (let a = k - LEFT; a < k; a++) if (!(low[k] < low[a])) return false
  for (let b = k + 1; b < k + 1 + right; b++) if (!(low[k] <= low[b])) return false
  return true
}

function isHigh(high: ArrayLike<number>, k: number, right: number): boolean {
  if (k < LEFT) return false
  for (let a = k - LEFT; a < k; a++) if (!(high[k] > high[a])) return false
  for (let b = k + 1; b < k + 1 + right; b++) if (!(high[k] >= high[b])) return false
  return true
}

export function strength(values: ArrayLike<number>, k: number, low: boolean): number {
  let s = 0
  while (s < MAX_STRENGTH && k - s - 1 >= 0) {
    const v = values[k - s - 1]
    if ((low && v <= values[k]) || (!low && v >= values[k])) break
    s++
  }
  return s
}

/** Confirmed swing lows and highs (bar indexes), in order. */
export function swings(high: ArrayLike<number>, low: ArrayLike<number>): { lows: number[]; highs: number[] } {
  const lows: number[] = []
  const highs: number[] = []
  for (let k = 0; k < low.length - RIGHT; k++) {
    if (isLow(low, k, RIGHT)) lows.push(k)
    if (isHigh(high, k, RIGHT)) highs.push(k)
  }
  return { lows, highs }
}

function pairs(points: number[], extra: number[], values: ArrayLike<number>, r: number[], low: boolean): Candidate[] {
  const out: Candidate[] = []
  const confirmed = new Set(points)
  for (const j of [...points, ...extra]) {
    if (Number.isNaN(r[j])) continue
    for (const i of points) {
      if (j - i < MIN_GAP || j - i > MAX_GAP || Number.isNaN(r[i])) continue
      const p1 = values[i]
      const p2 = values[j]
      const r1 = r[i]
      const r2 = r[j]
      let kind: Candidate['kind']
      if (low) {
        if (p2 < p1 && r2 > r1) kind = 'regular'
        else if (p2 > p1 && r2 < r1) kind = 'hidden'
        else continue
      } else {
        if (p2 > p1 && r2 < r1) kind = 'regular'
        else if (p2 < p1 && r2 > r1) kind = 'hidden'
        else continue
      }
      out.push({
        kind,
        direction: low ? 'LONG' : 'SHORT',
        i,
        j,
        confirm: confirmed.has(j) ? j + RIGHT : null,
        p1,
        p2,
        r1,
        r2,
        s1: strength(values, i, low),
        s2: strength(values, j, low),
      })
    }
  }
  return out
}

/** Every divergence candidate in the series, ordered by second swing, then direction, then first swing. */
export function find(high: ArrayLike<number>, low: ArrayLike<number>, close: ArrayLike<number>, includeForming = true): Candidate[] {
  const n = close.length
  const r = rsi(close)
  const { lows, highs } = swings(high, low)
  const formingLows: number[] = []
  const formingHighs: number[] = []
  if (includeForming) {
    for (let k = Math.max(LEFT, n - RIGHT); k < n; k++) {
      if (isLow(low, k, n - 1 - k)) formingLows.push(k)
      if (isHigh(high, k, n - 1 - k)) formingHighs.push(k)
    }
  }
  const found = [...pairs(lows, formingLows, low, r, true), ...pairs(highs, formingHighs, high, r, false)]
  return found.sort((a, b) => a.j - b.j || (a.direction < b.direction ? -1 : a.direction > b.direction ? 1 : 0) || a.i - b.i)
}
