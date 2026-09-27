import type { Outcome } from '../../api/types'

/** The PatternHorizonStat field prefix for an outcome ("big_up" -> big_up_rate, q_big_up, ...). */
export const targetOf = (o: Outcome | null) =>
  o === 'BIG_UP' ? 'big_up' : o === 'BIG_DOWN' ? 'big_down' : o === 'SIDEWAYS' ? 'sideways' : null
