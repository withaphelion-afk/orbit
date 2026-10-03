/**
 * Scores live divergences in the browser with the weights the backend publishes
 * (/api/divergences/model). The features mirror src/orbit/strategy/divergence_model.py
 * `features()`; the backend stays the scorer of record (it decides alerts that become
 * suggestions), this only lets the chart show a score the moment a divergence appears.
 */
import type { Asset, BarRow, DivergenceModel, Timeframe } from '../api/types'
import type { Candidate } from './divergence'

function rollingMean(x: number[], n: number): number[] {
  const out = new Array<number>(x.length).fill(NaN)
  let sum = 0
  for (let k = 0; k < x.length; k++) {
    sum += x[k]
    if (k >= n) sum -= x[k - n]
    if (k >= n - 1) out[k] = sum / n
  }
  return out
}

export interface ScoreContext {
  volMa5: number[]
  volMa20: number[]
  volPct: number[]
}

export function context(bars: BarRow[]): ScoreContext {
  const close = bars.map((b) => b[4])
  const ret = close.map((c, k) => (k ? Math.log(c / close[k - 1]) : 0))
  const vol = rollingMean(ret.map((r) => r * r), 20).map(Math.sqrt)
  const pct = close.map((_, k) => {
    if (k < 40) return 0.5
    const past = vol.slice(Math.max(19, k - 500), k + 1)
    return past.filter((v) => v < vol[k]).length / past.length
  })
  const volume = bars.map((b) => b[5])
  return { volMa5: rollingMean(volume, 5), volMa20: rollingMean(volume, 20), volPct: pct }
}

export function features(c: Candidate, bars: BarRow[], ctx: ScoreContext, asset: Asset, tf: Timeframe, regime: number): number[] {
  const close = bars.map((b) => b[4])
  const sign = c.direction === 'LONG' ? 1 : -1
  const k = c.confirm ?? bars.length - 1
  const priceChange = (c.p2 / c.p1 - 1) * sign
  const rsiChange = (c.r2 - c.r1) * sign
  const start = Math.max(0, c.i - 20)
  const trendBefore = c.i > start ? (close[c.i] / close[start] - 1) * sign : 0
  const v5 = ctx.volMa5[k]
  const v20 = ctx.volMa20[k]
  const volumeTrend = v20 && !Number.isNaN(v20) && !Number.isNaN(v5) ? Math.log((v5 + 1e-9) / (v20 + 1e-9)) : 0
  const extreme = (c.direction === 'LONG' && c.r1 < 30) || (c.direction === 'SHORT' && c.r1 > 70) ? 1 : 0
  const disagreement = Math.sign(rsiChange) * Math.log1p(Math.abs(rsiChange) / (Math.abs(priceChange) * 100 + 1))
  return [
    c.r1 / 100, c.r2 / 100, extreme, rsiChange / 100, priceChange, disagreement, (c.j - c.i) / 60, Math.log1p(c.s1), Math.log1p(c.s2),
    c.kind === 'hidden' ? 1 : 0, c.direction === 'LONG' ? 1 : 0, volumeTrend, trendBefore, regime * sign, ctx.volPct[k],
    +(tf === '1h'), +(tf === '4h'), +(tf === '1d'), +(tf === '1w'),
    +(asset === 'BTC'), +(asset === 'ETH'), +(asset === 'SOL'), +(asset === 'SILVER'),
  ]
}

/** The model's probability that this divergence works, or the plain rate before the model exists. */
export function score(m: DivergenceModel | undefined, x: number[]): number | null {
  if (!m?.model) return m?.base_rate ?? null
  const { mu, sd, coef } = m.model
  let z = coef[0]
  for (let k = 0; k < x.length; k++) z += ((x[k] - mu[k]) / sd[k]) * coef[k + 1]
  return 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, z))))
}
