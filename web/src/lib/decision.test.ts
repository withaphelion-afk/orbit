import { describe, expect, it } from 'vitest'
import { parsePrice, riskReward, validateLevels } from './decision'

describe('validateLevels', () => {
  it('accepts sane long and short levels', () => {
    expect(validateLevels('LONG', 100, 95, 110)).toBeNull()
    expect(validateLevels('SHORT', 100, 105, 90)).toBeNull()
  })

  it('rejects levels on the wrong side of entry', () => {
    expect(validateLevels('LONG', 100, 105, 110)).toMatch(/LONG/)
    expect(validateLevels('SHORT', 100, 95, 90)).toMatch(/SHORT/)
  })

  it('rejects non-numbers and non-positive prices', () => {
    expect(validateLevels('LONG', NaN, 95, 110)).toMatch(/POSITIVE/)
    expect(validateLevels('LONG', 100, 0, 110)).toMatch(/POSITIVE/)
  })
})

it('riskReward is target distance over stop distance', () => {
  expect(riskReward(100, 95, 110)).toBe(2)
})

it('parsePrice accepts thousands separators', () => {
  expect(parsePrice('64,210.50')).toBe(64210.5)
})
