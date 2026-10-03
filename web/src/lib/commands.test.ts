import { describe, expect, it } from 'vitest'
import { findInstruments, parseCommand } from './commands'

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

describe('findInstruments', () => {
  it('matches by code, terminal label, name or pair', () => {
    expect(findInstruments('xag')).toEqual(['SILVER'])
    expect(findInstruments('silver')).toEqual(['SILVER'])
    expect(findInstruments('bit')).toEqual(['BTC'])
    expect(findInstruments('usd')).toHaveLength(4)
  })
  it('lists everything for a blank query and nothing for a miss', () => {
    expect(findInstruments('  ')).toEqual(['BTC', 'ETH', 'SOL', 'SILVER'])
    expect(findInstruments('doge')).toEqual([])
  })
})
