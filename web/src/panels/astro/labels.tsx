import type { ConfidenceLabel, Outcome } from '../../api/types'

const LABEL_TEXT: Record<ConfidenceLabel, string> = {
  strong: 'STRONG',
  moderate: 'MODERATE',
  weak: 'WEAK',
  none: 'NONE',
  insufficient_data: 'TOO FEW',
}

const LABEL_HELP: Record<ConfidenceLabel, string> = {
  strong: 'Survives multiple-testing correction at q ≤ 0.05, with 25+ occurrences and a large effect',
  moderate: 'Survives multiple-testing correction at q ≤ 0.10',
  weak: 'Nominally significant (p < 0.05) but does not survive multiple-testing correction',
  none: 'Enough occurrences; no evidence beyond chance',
  insufficient_data: 'Fewer than 12 occurrences: not tested, never a signal',
}

export function ConfLabel({ label }: { label: ConfidenceLabel }) {
  return (
    <span className={`lab ${label}`} title={LABEL_HELP[label]}>
      {LABEL_TEXT[label]}
    </span>
  )
}

const OUTCOME_TEXT: Record<Outcome, string> = { BIG_UP: 'BIG ↑', BIG_DOWN: 'BIG ↓', SIDEWAYS: 'SIDEWAYS', NEUTRAL: 'NEUTRAL' }

export function OutcomeTag({ outcome }: { outcome: Outcome | null }) {
  if (!outcome) return <span className="dim">pending</span>
  return <span className={`oc ${outcome}`}>{OUTCOME_TEXT[outcome]}</span>
}
