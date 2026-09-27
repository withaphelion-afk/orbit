/** Small indicator helpers. Each returns one value per input, NaN until enough history exists. */

export function sma(values: number[], n: number): number[] {
  const out = new Array<number>(values.length).fill(NaN)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= n) sum -= values[i - n]
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}

/** Wilder's RSI. */
export function rsi(values: number[], n = 14): number[] {
  const out = new Array<number>(values.length).fill(NaN)
  let gain = 0
  let loss = 0
  for (let i = 1; i < values.length; i++) {
    const d = values[i] - values[i - 1]
    const g = Math.max(d, 0)
    const l = Math.max(-d, 0)
    if (i <= n) {
      gain += g
      loss += l
      if (i === n) {
        gain /= n
        loss /= n
        out[i] = 100 - 100 / (1 + gain / (loss || 1e-12))
      }
      continue
    }
    gain = (gain * (n - 1) + g) / n
    loss = (loss * (n - 1) + l) / n
    out[i] = 100 - 100 / (1 + gain / (loss || 1e-12))
  }
  return out
}

interface HLC {
  high: number
  low: number
  close: number
}

/** Simple-average true range. */
export function atr(bars: HLC[], n = 14): number[] {
  const tr = bars.map((b, i) =>
    i === 0 ? b.high - b.low : Math.max(b.high - b.low, Math.abs(b.high - bars[i - 1].close), Math.abs(b.low - bars[i - 1].close)),
  )
  return sma(tr, n)
}
