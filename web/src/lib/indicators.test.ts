import { describe, expect, it } from 'vitest'
import { atr, rsi, sma } from './indicators'

describe('sma', () => {
  it('averages the trailing window and pads the warm-up with NaN', () => {
    const out = sma([1, 2, 3, 4, 5], 3)
    expect(out.slice(0, 2).every(Number.isNaN)).toBe(true)
    expect(out.slice(2)).toEqual([2, 3, 4])
  })
})

describe('rsi', () => {
  it('is 100 for a series that only rises and near 0 for one that only falls', () => {
    const up = Array.from({ length: 30 }, (_, i) => 100 + i)
    const down = up.slice().reverse()
    expect(rsi(up).at(-1)).toBeCloseTo(100, 5)
    expect(rsi(down).at(-1)!).toBeLessThan(1e-6)
  })

  it('stays within 0-100', () => {
    const zigzag = Array.from({ length: 60 }, (_, i) => 100 + Math.sin(i) * 5)
    for (const v of rsi(zigzag).filter((x) => !Number.isNaN(x))) {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(100)
    }
  })
})

describe('atr', () => {
  it('uses gaps from the previous close, not just the bar range', () => {
    const bars = [
      { high: 10, low: 9, close: 9.5 },
      { high: 12, low: 11, close: 11.5 }, // gap up: true range 12 - 9.5 = 2.5
    ]
    expect(atr(bars, 2)[1]).toBeCloseTo((1 + 2.5) / 2)
  })
})
