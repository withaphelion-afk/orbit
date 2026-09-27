import { describe, expect, it } from 'vitest'
import { ASSETS } from '../config'
import { createMockSource } from './mock'

const NOW = Date.UTC(2026, 8, 27, 14, 0, 0)

describe('mock source', () => {
  it('is deterministic for a given seed and time', async () => {
    const a = await createMockSource({ now: NOW }).suggestions()
    const b = await createMockSource({ now: NOW }).suggestions()
    expect(a).toEqual(b)
  })

  it('serves one quote and a full candle history per tracked asset', async () => {
    const src = createMockSource({ now: NOW })
    const quotes = await src.quotes()
    expect(quotes.map((q) => q.asset)).toEqual(ASSETS)
    for (const a of ASSETS) {
      const candles = await src.candles(a)
      expect(candles.length).toBe(240)
      for (const c of candles) expect(c.low).toBeLessThanOrEqual(Math.min(c.open, c.close))
    }
  })

  it('puts stops and targets on the correct side of entry', async () => {
    for (const { suggestion: s, risk_reward } of await createMockSource({ now: NOW }).suggestions()) {
      const sd = s.direction === 'LONG' ? 1 : -1
      expect(sd * (s.entry_price - s.stop_loss)).toBeGreaterThan(0)
      expect(sd * (s.take_profit - s.entry_price)).toBeGreaterThan(0)
      expect(risk_reward).toBeGreaterThan(1)
      expect(s.confidence).toBeGreaterThan(0)
      expect(s.confidence).toBeLessThanOrEqual(1)
    }
  })

  it('moves a decided suggestion from the queue to the top of the journal', async () => {
    const src = createMockSource({ now: NOW })
    const [first] = await src.suggestions()
    const before = (await src.journal()).length
    const row = await src.decide(first.id, { decision: 'MODIFIED', notes: 'tighter stop', stop_loss: first.suggestion.stop_loss * 1.01 })
    expect(row.entry.decision).toBe('MODIFIED')
    expect(row.entry.suggestion.stop_loss).toBeCloseTo(first.suggestion.stop_loss * 1.01)
    expect((await src.suggestions()).find((s) => s.id === first.id)).toBeUndefined()
    const journal = await src.journal()
    expect(journal.length).toBe(before + 1)
    expect(journal[0].id).toBe(row.id)
    await expect(src.decide(first.id, { decision: 'TAKEN', notes: '' })).rejects.toThrow(/no longer pending/)
  })
})
