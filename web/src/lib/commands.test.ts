import { describe, expect, it } from 'vitest'
import { complete, parseCommand } from './commands'

describe('parseCommand', () => {
  it('reads an asset and a function in either order', () => {
    expect(parseCommand('SOL GP')).toEqual({ asset: 'SOL', view: 'GP' })
    expect(parseCommand('drift btc')).toEqual({ asset: 'BTC', view: 'DRIFT' })
  })

  it('maps the XAG label and SILVER code to the same asset', () => {
    expect(parseCommand('XAG')).toEqual({ asset: 'SILVER' })
    expect(parseCommand('silver gp')).toEqual({ asset: 'SILVER', view: 'GP' })
  })

  it('ignores a trailing <GO>', () => {
    expect(parseCommand('SUGG <GO>')).toEqual({ view: 'SUGG' })
    expect(parseCommand('eth go')).toEqual({ asset: 'ETH' })
  })

  it('returns null for blank input and an error for unknown tokens', () => {
    expect(parseCommand('   ')).toBeNull()
    expect(parseCommand('SOL FOO')).toEqual({ error: 'UNKNOWN COMMAND "FOO". TYPE HELP' })
  })
})

describe('complete', () => {
  it('extends a prefix and never echoes a finished command', () => {
    expect(complete('su')).toBe('SUGG')
    expect(complete('xag d')).toBe('XAG DRIFT')
    expect(complete('SUGG')).toBeNull()
    expect(complete('')).toBeNull()
  })
})
