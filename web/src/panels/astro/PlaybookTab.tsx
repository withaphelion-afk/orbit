import { useMemo, useState } from 'react'
import { usePattern, usePlaybook, usePlaybookOverview } from '../../api/hooks'
import { ApiError } from '../../api/http'
import type { Asset, ConfidenceLabel, HorizonStatBase, PatternHorizonStat, PatternSummary } from '../../api/types'
import { Empty, QueryState, Seg } from '../../components/bits'
import { ASSET_META } from '../../config'
import { RunControl } from '../../components/RunControl'
import { day, hhmm, num, pct, pval, signed, tone, transitLabel } from '../../lib/format'
import { IntradayChart } from './IntradayChart'
import { ConfLabel, OutcomeTag } from './labels'
import { targetOf } from './targets'

type Filter = 'EVIDENCE' | 'TESTED' | 'TOO FEW' | 'ALL'
const FILTERS: Filter[] = ['EVIDENCE', 'TESTED', 'TOO FEW', 'ALL']
const EVIDENCE: ConfidenceLabel[] = ['strong', 'moderate', 'weak']

function keep(p: PatternSummary, f: Filter) {
  if (f === 'ALL') return p.n_events > 0
  if (f === 'EVIDENCE') return EVIDENCE.includes(p.label)
  if (f === 'TESTED') return p.label !== 'insufficient_data'
  return p.label === 'insufficient_data' && p.n_events > 0
}

function headline(p: { horizons: PatternHorizonStat[]; headline_horizon: number | null; dominant_outcome: PatternSummary['dominant_outcome'] }) {
  const h = p.horizons.find((x) => x.horizon_days === p.headline_horizon)
  const t = targetOf(p.dominant_outcome)
  if (!h || !t) return null
  return {
    h,
    rate: h[`${t}_rate`],
    base: h[`base_${t}_rate`],
    q: h[`q_${t}`],
  }
}

export function PlaybookTab({ asset }: { asset: Asset }) {
  const overview = usePlaybookOverview()
  const book = usePlaybook(asset)
  const [filter, setFilter] = useState<Filter>('TESTED')
  const [selected, setSelected] = useState<string | null>(null)

  const rows = useMemo(() => (book.data?.patterns ?? []).filter((p) => keep(p, filter)), [book.data, filter])
  const counts = useMemo(() => {
    const c: Partial<Record<ConfidenceLabel, number>> = {}
    for (const p of book.data?.patterns ?? []) if (p.n_events > 0) c[p.label] = (c[p.label] ?? 0) + 1
    return c
  }, [book.data])

  if (!book.data) {
    if (book.error instanceof ApiError && book.error.status === 404) {
      return (
        <>
          <RunControl />
          <Empty title="PLAYBOOK NOT BUILT YET">
            <span>
              Press RUN ANALYSIS above, or run <code>uv run python scripts/build_playbook.py</code>.
            </span>
          </Empty>
        </>
      )
    }
    return <QueryState isPending={book.isPending} error={book.error} what="the playbook" />
  }
  const pb = book.data
  const o = overview.data
  const family = o?.tests_by_family[`${asset}:PATTERNS`]
  const current = selected && pb.patterns.some((p) => p.pattern_id === selected) ? selected : null

  return (
    <div className="pbk">
      <RunControl compact />
      <div className="pbk-head">
        <div>
          <span className="lbl">History</span>
          <span className="v">
            {day(pb.history_start)} {new Date(pb.history_start).getUTCFullYear()} → {day(pb.history_end)} {new Date(pb.history_end).getUTCFullYear()}
          </span>
          <span className="dim">
            {num(pb.bars, 0)} daily · {pb.hourly_bars ? `${num(pb.hourly_bars, 0)} hourly from ${new Date(pb.hourly_start!).getUTCFullYear()}` : 'no hourly bars yet'}
          </span>
        </div>
        <div>
          <span className="lbl">Tests corrected together</span>
          <span className="v">{family ?? '—'}</span>
          <span className="dim">BH FDR within {ASSET_META[asset].label}</span>
        </div>
        <div>
          <span className="lbl">Placebo check</span>
          {o?.placebo ? (
            <>
              <span className={`v ${o.placebo.runs_with_any_discovery ? 'warn' : 'up'}`}>
                {o.placebo.runs_with_any_discovery} / {o.placebo.placebo_runs}
              </span>
              <span className="dim">fake-calendar runs with a false discovery</span>
            </>
          ) : (
            <>
              <span className="v dim">not run</span>
              <span className="dim">scripts/placebo_check.py</span>
            </>
          )}
        </div>
        <div>
          <span className="lbl">Built</span>
          <span className="v">{day(pb.generated_at)}</span>
          <span className="dim">run #{o?.runs_so_far ?? '—'} on this data</span>
        </div>
        <div className="pbk-counts">
          {(['strong', 'moderate', 'weak', 'none', 'insufficient_data'] as ConfidenceLabel[]).map((l) => (
            <span key={l}>
              <ConfLabel label={l} /> {counts[l] ?? 0}
            </span>
          ))}
        </div>
      </div>
      <div className="pbk-body">
        <div className="pbk-list">
          <div className="pbk-tools">
            <Seg label="Filter" value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ label: f, value: f }))} />
            <span className="dim">{rows.length} patterns</span>
          </div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="l">Label</th>
                  <th className="l">Pattern</th>
                  <th>n</th>
                  <th className="l">Leans</th>
                  <th>Rate · base</th>
                  <th>Mean</th>
                  <th>q</th>
                  <th className="l" title="The same test at hourly resolution, from the exact moment">Hourly</th>
                  <th title="Occurrences that didn't match the dominant outcome">Exc</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const hl = headline(p)
                  return (
                    <tr key={p.pattern_id} className={`click ${p.pattern_id === current ? 'sel' : ''}`} onClick={() => setSelected(p.pattern_id)}>
                      <td className="l">
                        <ConfLabel label={p.label} />
                      </td>
                      <td className="l">{p.description}</td>
                      <td>{p.n_events}</td>
                      <td className="l">
                        {hl ? (
                          <>
                            <OutcomeTag outcome={p.dominant_outcome} /> <span className="dim">{p.headline_horizon}d</span>
                          </>
                        ) : (
                          <span className="dim">—</span>
                        )}
                      </td>
                      <td>{hl ? `${pct(hl.rate)} · ${pct(hl.base)}` : '—'}</td>
                      <td className={hl ? tone(hl.h.mean_return) : ''}>{hl ? `${signed(hl.h.mean_return * 100, 1)}%` : '—'}</td>
                      <td>{pval(hl?.q)}</td>
                      <td className="l">{p.timing.length ? <ConfLabel label={p.timing_label} /> : <span className="dim">—</span>}</td>
                      <td>{p.exceptions || ''}</td>
                    </tr>
                  )
                })}
                {!rows.length && (
                  <tr>
                    <td colSpan={9} className="l dim empty-row">
                      {filter === 'EVIDENCE' ? 'No pattern shows evidence beyond chance for this asset.' : 'No patterns match.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="pbk-detail">{current ? <PatternDetail asset={asset} id={current} /> : <DetailHint />}</div>
      </div>
    </div>
  )
}

function DetailHint() {
  return (
    <div className="empty">
      <b>SELECT A PATTERN</b>
      <span>Every occurrence is listed with what followed, and the ones that went against the pattern are flagged with their context.</span>
      <span className="dim">
        Labels: STRONG and MODERATE survive multiple-testing correction; WEAK is nominal only; TOO FEW means under 12 occurrences, never tested.
      </span>
    </div>
  )
}

function HorizonTable({ rows, unit, headline }: { rows: (HorizonStatBase & { h: number })[]; unit: 'd' | 'h'; headline: number | null }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl hz">
        <thead>
          <tr>
            <th>{unit === 'd' ? 'Days' : 'Hours'}</th>
            <th>n</th>
            <th>Big ↑ · base</th>
            <th>q</th>
            <th>Big ↓ · base</th>
            <th>q</th>
            <th>Sideways · base</th>
            <th>q</th>
            <th>Mean</th>
            <th>Win</th>
            <th title="Exact probability against uniformly random dates (not corrected)">Uniform p</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.h} className={h.h === headline ? 'sel' : ''}>
              <td>
                {h.h}
                {unit}
              </td>
              <td>{h.n}</td>
              <td>
                {pct(h.big_up_rate)} · <span className="dim">{pct(h.base_big_up_rate)}</span>
              </td>
              <td>{pval(h.q_big_up)}</td>
              <td>
                {pct(h.big_down_rate)} · <span className="dim">{pct(h.base_big_down_rate)}</span>
              </td>
              <td>{pval(h.q_big_down)}</td>
              <td>
                {pct(h.sideways_rate)} · <span className="dim">{pct(h.base_sideways_rate)}</span>
              </td>
              <td>{pval(h.q_sideways)}</td>
              <td className={tone(h.mean_return)}>{signed(h.mean_return * 100, unit === 'd' ? 1 : 2)}%</td>
              <td>{pct(h.win_rate)}</td>
              <td className="dim">{pval(h.p_uniform_best)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const hrs = (v: number | null) => (v === null ? '—' : `+${num(v, 0)}h`)

function PatternDetail({ asset, id }: { asset: Asset; id: string }) {
  const { data: p, isPending, error } = usePattern(asset, id)
  const [onlyExceptions, setOnlyExceptions] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  if (!p) return <QueryState isPending={isPending} error={error} what="the pattern" />
  const occ = onlyExceptions ? p.occurrences.filter((o) => o.is_exception) : p.occurrences
  const exceptions = p.occurrences.filter((o) => o.is_exception).length
  const hasHourly = p.occurrences.some((o) => o.pre_move_return !== null)
  const opened = occ.find((o) => o.date === open) ?? null

  return (
    <div className="pd">
      <div className="pd-head">
        <ConfLabel label={p.label} />
        <span className="pd-title">{p.description}</span>
        <span className="dim">
          {p.n_events} occurrences · score {p.score}
        </span>
      </div>
      <p className="pd-summary">{p.summary}</p>
      <span className="lbl">Daily bars, from the day of the transit</span>
      <HorizonTable rows={p.horizons.map((h) => ({ ...h, h: h.horizon_days }))} unit="d" headline={p.headline_horizon} />

      {p.timing.length > 0 && (
        <>
          <div className="pd-head">
            <span className="lbl">Hourly bars, from the exact moment</span>
            <ConfLabel label={p.timing_label} />
          </div>
          {p.timing_summary && <p className="pd-summary">{p.timing_summary}</p>}
          <HorizonTable rows={p.timing.map((h) => ({ ...h, h: h.horizon_hours }))} unit="h" headline={p.timing_headline_hours} />
        </>
      )}

      {p.occurrences.length > 0 && (
        <>
          <div className="pd-occ-head">
            <span className="lbl">
              Occurrences at {p.headline_horizon}d · {exceptions} against the pattern{hasHourly ? ' · click a row for its hourly chart' : ''}
            </span>
            <Seg
              label="Show"
              value={onlyExceptions ? 'EXC' : 'ALL'}
              onChange={(v) => setOnlyExceptions(v === 'EXC')}
              options={[
                { label: 'ALL', value: 'ALL' },
                { label: 'EXCEPTIONS', value: 'EXC' },
              ]}
            />
          </div>
          {opened && p.headline_horizon !== null && <IntradayChart asset={asset} occ={opened} windowDays={p.headline_horizon} />}
          <div className="tbl-wrap">
            <table className="tbl occ">
              <thead>
                <tr>
                  <th className="l">Date</th>
                  <th className="l">Exact (UTC)</th>
                  <th className="l">Event</th>
                  <th className="l">Outcome</th>
                  <th>Return</th>
                  {hasHourly && (
                    <>
                      <th title="Price change over the 72 hours before the exact moment">72h before</th>
                      <th title="Hours after the exact moment until price had moved one normal day's range (daily ATR) in the move's direction">Move began</th>
                      <th title="When the largest move in that direction within the window came, and its size">Peak</th>
                    </>
                  )}
                  <th className="l">Regime</th>
                  <th title="20-day realised volatility vs this asset's own history">Vol pct</th>
                  <th className="l">Also in the window</th>
                </tr>
              </thead>
              <tbody>
                {occ
                  .slice()
                  .reverse()
                  .map((o) => (
                    <tr
                      key={o.date}
                      className={`${o.is_exception ? 'exc' : ''} ${o.pre_move_return !== null ? 'click' : ''} ${o.date === open ? 'sel' : ''}`}
                      onClick={() => o.pre_move_return !== null && setOpen(o.date === open ? null : o.date)}
                    >
                      <td className="l">
                        {day(o.date)} {new Date(o.date).getUTCFullYear()}
                      </td>
                      <td className="l mid">{o.event.exact_time ? hhmm(o.event.exact_time) : '—'}</td>
                      <td className="l">{transitLabel(o.event)}</td>
                      <td className="l">
                        <OutcomeTag outcome={o.outcome} />
                      </td>
                      <td className={o.forward_return === null ? 'dim' : tone(o.forward_return)}>
                        {o.forward_return === null ? '—' : `${signed(o.forward_return * 100, 1)}%`}
                      </td>
                      {hasHourly && (
                        <>
                          <td className={o.pre_move_return === null ? 'dim' : tone(o.pre_move_return)}>
                            {o.pre_move_return === null ? '—' : `${signed(o.pre_move_return * 100, 1)}%`}
                          </td>
                          <td>{hrs(o.hours_to_move)}</td>
                          <td className={o.peak_return === null ? 'dim' : tone(o.peak_return)}>
                            {o.peak_return === null ? '—' : `${hrs(o.hours_to_peak)} · ${signed(o.peak_return * 100, 1)}%`}
                          </td>
                        </>
                      )}
                      <td className="l">
                        {o.regime ?? <span className="dim">n/a</span>}
                        {o.regime && o.regime_scope === 'OWN' && <span className="dim"> (own)</span>}
                      </td>
                      <td>{o.volatility_percentile === null ? '—' : pct(o.volatility_percentile)}</td>
                      <td className="l note">
                        {o.conflicting_events.length > 0 && <span className="warn">Conflicting: {o.conflicting_events.join('; ')}. </span>}
                        {o.concurrent_events.length > 0 ? <span className="dim">{o.concurrent_events.join(', ')}</span> : <span className="dim">—</span>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {p.speed_class === 'LUNAR' && <p className="dim pd-summary">Moon occurrences aren't listed individually (thousands of them); the aggregates above cover all of them.</p>}
    </div>
  )
}
