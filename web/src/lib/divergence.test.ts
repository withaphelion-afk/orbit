import { describe, expect, it } from 'vitest'
import raw from '../../../tests/fixtures/divergence_cases.json?raw'
import { find, rsi, swings } from './divergence'

/** The same file tests/test_strategy.py checks the Python version against: both must agree exactly. */
const cases = JSON.parse(raw) as {
  name: string
  high: number[]
  low: number[]
  close: number[]
  rsi: (number | null)[]
  swings: { lows: number[]; highs: number[] }
  expected: { kind: string; direction: string; i: number; j: number; confirm: number | null; r1: number; r2: number; s1: number; s2: number }[]
}[]

describe('divergence detection matches the Python version', () => {
  for (const c of cases) {
    it(c.name, () => {
      const r = rsi(c.close)
      c.rsi.forEach((x, k) => (x === null ? expect(r[k]).toBeNaN() : expect(r[k]).toBeCloseTo(x, 9)))
      expect(swings(c.high, c.low)).toEqual(c.swings)
      const got = find(c.high, c.low, c.close)
      expect(got.length).toBe(c.expected.length)
      got.forEach((g, k) => {
        const e = c.expected[k]
        expect([g.kind, g.direction, g.i, g.j, g.confirm, g.s1, g.s2]).toEqual([e.kind, e.direction, e.i, e.j, e.confirm, e.s1, e.s2])
        expect(g.r1).toBeCloseTo(e.r1, 9)
        expect(g.r2).toBeCloseTo(e.r2, 9)
      })
    })
  }
})
