import { CalendarRange, ChartColumn, ChevronRight, Clock, FlaskConical, Gauge, Hammer, Search, Sigma, X } from 'lucide-react'
import { useMemo, useState, type KeyboardEvent } from 'react'
import { usePattern, usePlaybook, usePlaybookOverview } from '../../api/hooks'
import { ApiError } from '../../api/http'
import type { Asset, ConfidenceLabel, HorizonStatBase, PatternHorizonStat, PatternOccurrence, PatternSummary } from '../../api/types'
import { Empty, QueryState, Seg, StatCard, StatGrid } from '../../components/bits'
import { ASSET_META } from '../../config'
import { RunControl } from '../../components/RunControl'
import { day, hhmm, num, pct, pval, signed, tone, transitLabel } from '../../lib/format'
import { IntradayChart } from './IntradayChart'
import { ConfLabel, OutcomeTag } from './labels'
import { targetOf } from './targets'

type Filter = 'EVIDENCE' | 'TESTED' | 'TOO FEW' | 'ALL'
const FILTERS: Filter[] = ['EVIDENCE', 'TESTED', 'TOO FEW', 'ALL']
const EVIDENCE: ConfidenceLabel[] = ['strong', 'moderate', 'weak']
const LABELS: ConfidenceLabel[] = ['strong', 'moderate', 'weak', 'none', 'insufficient_data']
const RANK: Record<ConfidenceLabel, number> = { strong: 4, moderate: 3, weak: 2, none: 1, insufficient_data: 0 }
const ICON = { size: 18, strokeWidth: 1.75 } as const

type SortKey = 'label' | 'pattern' | 'n' | 'score'
type Sort = { key: SortKey; dir: 1 | -1 } | null

function keep(p: PatternSummary, f: Filter) {
  if (f === 'ALL') return p.n_events > 0
  if (f === 'EVIDENCE') return EVIDENCE.includes(p.label)
  if (f === 'TESTED') return p.label !== 'insufficient_data'
  return p.label === 'insufficient_data' && p.n_events > 0
}

function compare(a: PatternSummary, b: PatternSummary, key: SortKey) {
  if (key === 'label') return RANK[a.label] - RANK[b.label] || a.score - b.score
  if (key === 'pattern') return a.description.localeCompare(b.description)
  if (key === 'n') return a.n_events - b.n_events
  return a.score - b.score
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

const year = (iso: string) => new Date(iso).getUTCFullYear()

export function PlaybookTab({ asset }: { asset: Asset }) {
  const overview = usePlaybookOverview()
  const book = usePlaybook(asset)
  const [filter, setFilter] = useState<Filter>('TESTED')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const out = (book.data?.patterns ?? []).filter(
      (p) => keep(p, filter) && (!q || p.description.toLowerCase().includes(q) || p.pattern_id.toLowerCase().includes(q) || (p.sign ?? '').toLowerCase().includes(q)),
    )
    if (sort) out.sort((a, b) => compare(a, b, sort.key) * sort.dir)
    return out
  }, [book.data, filter, query, sort])
  const counts = useMemo(() => {
    const c: Partial<Record<ConfidenceLabel, number>> = {}
    for (const p of book.data?.patterns ?? []) if (p.n_events > 0) c[p.label] = (c[p.label] ?? 0) + 1
    return c
  }, [book.data])

  if (!book.data) {
    if (book.error instanceof ApiError && book.error.status === 404) {
      return (
        <div className="pbk">
          <RunControl />
          <Empty title="PLAYBOOK NOT BUILT YET">
            <span>
              Press RUN ANALYSIS above, or run <code>uv run python scripts/build_playbook.py</code>.
            </span>
          </Empty>
        </div>
      )
    }
    return <QueryState isPending={book.isPending} error={book.error} what="the playbook" />
  }
  const pb = book.data
  const o = overview.data
  const family = o?.tests_by_family[`${asset}:PATTERNS`]
  const current = selected && pb.patterns.some((p) => p.pattern_id === selected) ? selected : null
  const total = LABELS.reduce((s, l) => s + (counts[l] ?? 0), 0)

  const onSort = (key: SortKey) => setSort((s) => (s?.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'pattern' ? 1 : -1 }))
  const sortTh = (key: SortKey, text: string, className: string, title: string) => (
    <th
      className={`sort ${className}`}
      title={title}
      tabIndex={0}
      aria-sort={sort?.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
      onClick={() => onSort(key)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSort(key)
        }
      }}
    >
      {text}
      {sort?.key === key && <span className="ar"> {sort.dir === 1 ? '↑' : '↓'}</span>}
    </th>
  )
  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape' && query) {
      e.stopPropagation()
      setQuery('')
    }
  }

  return (
    <div className="pbk">
      <RunControl compact />
      <StatGrid>
        <StatCard
          icon={<CalendarRange {...ICON} />}
          label="History"
          value={`${num((Date.parse(pb.history_end) - Date.parse(pb.history_start)) / (365.25 * 86_400_000), 1)} years`}
          caption={`${day(pb.history_start)} ${year(pb.history_start)} → ${day(pb.history_end)} ${year(pb.history_end)}`}
        />
        <StatCard icon={<ChartColumn {...ICON} />} label="Daily bars" value={num(pb.bars, 0)} caption="used for the day-by-day tests" />
        <StatCard
          icon={<Clock {...ICON} />}
          label="Hourly bars"
          value={pb.hourly_bars ? num(pb.hourly_bars, 0) : 'none yet'}
          tone={pb.hourly_bars ? undefined : 'dim'}
          caption={pb.hourly_bars ? `from ${year(pb.hourly_start!)}` : 'no hourly bars yet'}
        />
        <StatCard
          icon={<Sigma {...ICON} />}
          label="Tests"
          value={family ?? '—'}
          caption={`corrected together · BH FDR within ${ASSET_META[asset].label}`}
          title="Tests corrected together for multiple testing (Benjamini–Hochberg false discovery rate)"
        />
        {o?.placebo ? (
          <StatCard
            icon={<FlaskConical {...ICON} />}
            label="Placebo check"
            value={`${o.placebo.runs_with_any_discovery} / ${o.placebo.placebo_runs}`}
            tone={o.placebo.runs_with_any_discovery ? 'warn' : 'up'}
            caption="fake-calendar runs with a false discovery"
          />
        ) : (
          <StatCard icon={<FlaskConical {...ICON} />} label="Placebo check" value="not run" tone="dim" caption="scripts/placebo_check.py" />
        )}
        <StatCard icon={<Hammer {...ICON} />} label="Built" value={day(pb.generated_at)} caption={`run #${o?.runs_so_far ?? '—'} on this data`} />
        <div className="stat pbk-strength">
          <span className="stat-ico">
            <Gauge {...ICON} />
          </span>
          <div className="stat-body">
            <span className="stat-lbl">Signal strength · patterns with occurrences</span>
            <div className="pbk-counts">
              {LABELS.map((l) => (
                <span key={l}>
                  <ConfLabel label={l} /> <b>{counts[l] ?? 0}</b>
                </span>
              ))}
            </div>
            {total > 0 && (
              <div className="pbk-dist" aria-hidden>
                {LABELS.map((l) => (counts[l] ? <i key={l} className={l} style={{ flexGrow: counts[l] }} /> : null))}
              </div>
            )}
          </div>
        </div>
      </StatGrid>
      <div className="pbk-body">
        <div className="pbk-list">
          <div className="pbk-tools">
            <Seg label="Filter" value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ label: f, value: f }))} />
            <label className="pbk-search">
              <Search size={15} strokeWidth={1.75} aria-hidden className="pbk-search-ico" />
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onSearchKey} placeholder="Search patterns" aria-label="Search patterns" />
              {query && (
                <button type="button" className="pbk-search-x" onClick={() => setQuery('')} title="Clear search (Esc)" aria-label="Clear search">
                  <X size={14} strokeWidth={1.75} />
                </button>
              )}
            </label>
            <span className="pbk-count">{rows.length} patterns</span>
          </div>
          <div className="tbl-wrap">
            <table className="tbl pbk-tbl">
              <thead>
                <tr>
                  {sortTh('label', 'Label', 'l', 'Sort by signal strength')}
                  {sortTh('pattern', 'Pattern', 'l', 'Sort by pattern name')}
                  {sortTh('n', 'n', '', 'Sort by number of occurrences')}
                  <th title="Mean return at the headline horizon">Mean</th>
                  <th title="Multiple-testing-corrected p for the leaning outcome at the headline horizon">q</th>
                  <th className="l" title="The same test at hourly resolution, from the exact moment">
                    Hourly
                  </th>
                  <th title="Occurrences that didn't match the dominant outcome">Exc</th>
                  {sortTh('score', 'Score', '', 'Sort by the analysis score')}
                  <th aria-hidden />
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
                      <td className="l pbk-pat">
                        <span className="pbk-name">{p.description}</span>
                        <span className="pbk-sub" title="Leans: the dominant outcome at the headline horizon, its rate and the base rate">
                          {hl ? (
                            <>
                              <OutcomeTag outcome={p.dominant_outcome} /> {p.headline_horizon}d · {pct(hl.rate)} vs {pct(hl.base)} base
                            </>
                          ) : (
                            '—'
                          )}
                        </span>
                      </td>
                      <td>{p.n_events}</td>
                      <td className={hl ? tone(hl.h.mean_return) : 'dim'}>{hl ? `${signed(hl.h.mean_return * 100, 1)}%` : '—'}</td>
                      <td>{pval(hl?.q)}</td>
                      <td className="l">{p.timing.length ? <ConfLabel label={p.timing_label} /> : <span className="dim">—</span>}</td>
                      <td>{p.exceptions || ''}</td>
                      <td className="mid">{p.score}</td>
                      <td className="chev">
                        <ChevronRight size={15} strokeWidth={1.75} aria-hidden />
                      </td>
                    </tr>
                  )
                })}
                {!rows.length && (
                  <tr>
                    <td colSpan={9} className="l dim empty-row">
                      {query.trim()
                        ? `No patterns match "${query.trim()}".`
                        : filter === 'EVIDENCE'
                          ? 'No pattern shows evidence beyond chance for this asset.'
                          : 'No patterns match.'}
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
    <div className="empty pbk-hint">
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
    <div className="tbl-wrap pd-card">
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
            <tr key={h.h} className={h.h === headline ? 'sel' : ''} title={h.h === headline ? 'Headline horizon' : undefined}>
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
const ret = (v: number | null) => (v === null ? '—' : `${signed(v * 100, 1)}%`)
const retTone = (v: number | null) => (v === null ? 'dim' : tone(v))
const when = (o: PatternOccurrence) => `${day(o.date)} ${year(o.date)}`

type Sub = 'DAILY' | 'HOURLY' | 'OCCURRENCES' | 'CONTEXT'

function PatternDetail({ asset, id }: { asset: Asset; id: string }) {
  const { data: p, isPending, error } = usePattern(asset, id)
  const [sub, setSub] = useState<Sub>('DAILY')
  const [onlyExceptions, setOnlyExceptions] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  if (!p) return <QueryState isPending={isPending} error={error} what="the pattern" />
  const occ = (onlyExceptions ? p.occurrences.filter((o) => o.is_exception) : p.occurrences).slice().reverse()
  const exceptions = p.occurrences.filter((o) => o.is_exception).length
  const hasHourly = p.occurrences.some((o) => o.pre_move_return !== null)
  const opened = occ.find((o) => o.date === open) ?? null

  const lunarNote = p.speed_class === 'LUNAR' && (
    <p className="dim pd-summary">Moon occurrences aren't listed individually (thousands of them); the aggregates cover all of them.</p>
  )
  const showSeg = (
    <Seg
      label="Show"
      value={onlyExceptions ? 'EXC' : 'ALL'}
      onChange={(v) => setOnlyExceptions(v === 'EXC')}
      options={[
        { label: 'ALL', value: 'ALL' },
        { label: `EXCEPTIONS ${exceptions}`, value: 'EXC' },
      ]}
    />
  )
  const noOccurrences = (
    <>
      <Empty title="NO OCCURRENCES LISTED">{!lunarNote && <span>This pattern has no individual occurrences to show.</span>}</Empty>
      {lunarNote}
    </>
  )

  return (
    <div className="pd">
      <div className="pd-top">
        <div className="pd-head">
          <ConfLabel label={p.label} />
          <span className="pd-title">{p.description}</span>
        </div>
        <span className="pd-meta">
          {p.n_events} occurrences · score {p.score}
        </span>
        <p className="pd-summary">{p.summary}</p>
        <Seg
          label="Detail"
          value={sub}
          onChange={setSub}
          options={[
            { label: 'DAILY BARS', value: 'DAILY' },
            { label: 'HOURLY BARS', value: 'HOURLY' },
            { label: 'OCCURRENCES', value: 'OCCURRENCES' },
            { label: 'CONTEXT', value: 'CONTEXT' },
          ]}
        />
      </div>

      <div className="pd-body">
        {sub === 'DAILY' && (
          <>
            <span className="lbl">Daily bars, from the day of the transit</span>
            <HorizonTable rows={p.horizons.map((h) => ({ ...h, h: h.horizon_days }))} unit="d" headline={p.headline_horizon} />
            {lunarNote}
          </>
        )}

        {sub === 'HOURLY' &&
          (p.timing.length > 0 ? (
            <>
              <div className="pd-sec">
                <span className="lbl">Hourly bars, from the exact moment</span>
                <ConfLabel label={p.timing_label} />
              </div>
              {p.timing_summary && <p className="pd-summary">{p.timing_summary}</p>}
              <HorizonTable rows={p.timing.map((h) => ({ ...h, h: h.horizon_hours }))} unit="h" headline={p.timing_headline_hours} />
            </>
          ) : (
            <Empty title="NO HOURLY TEST">
              <span>This pattern has no hourly-bar test. The HOURLY column in the list shows which patterns have one.</span>
            </Empty>
          ))}

        {sub === 'OCCURRENCES' &&
          (p.occurrences.length === 0 ? (
            noOccurrences
          ) : (
            <>
              <div className="pd-sec">
                <span className="lbl">
                  Occurrences at {p.headline_horizon}d · {exceptions} against the pattern{hasHourly ? ' · click a row for its hourly chart' : ''}
                </span>
                {showSeg}
              </div>
              {opened && p.headline_horizon !== null && <IntradayChart asset={asset} occ={opened} windowDays={p.headline_horizon} />}
              <div className="tbl-wrap pd-card">
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
                          <th aria-hidden />
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {occ.map((o) => {
                      const can = o.pre_move_return !== null
                      return (
                        <tr
                          key={o.date}
                          className={`${o.is_exception ? 'exc' : ''} ${can ? 'click' : ''} ${o.date === open ? 'sel' : ''}`}
                          onClick={() => can && setOpen(o.date === open ? null : o.date)}
                          title={can ? (o.date === open ? 'Hide the hourly chart' : 'Show the hourly chart around this occurrence') : undefined}
                        >
                          <td className="l">{when(o)}</td>
                          <td className="l mid">{o.event.exact_time ? hhmm(o.event.exact_time) : '—'}</td>
                          <td className="l">{transitLabel(o.event)}</td>
                          <td className="l">
                            <OutcomeTag outcome={o.outcome} />
                          </td>
                          <td className={retTone(o.forward_return)}>{ret(o.forward_return)}</td>
                          {hasHourly && (
                            <>
                              <td className={retTone(o.pre_move_return)}>{ret(o.pre_move_return)}</td>
                              <td>{hrs(o.hours_to_move)}</td>
                              <td className={retTone(o.peak_return)}>{o.peak_return === null ? '—' : `${hrs(o.hours_to_peak)} · ${ret(o.peak_return)}`}</td>
                              <td className="chev">{can && <ChevronRight size={15} strokeWidth={1.75} aria-hidden className={o.date === open ? 'open' : ''} />}</td>
                            </>
                          )}
                        </tr>
                      )
                    })}
                    {!occ.length && (
                      <tr>
                        <td colSpan={hasHourly ? 9 : 5} className="l dim empty-row">
                          No occurrence went against the pattern.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {lunarNote}
            </>
          ))}

        {sub === 'CONTEXT' &&
          (p.occurrences.length === 0 ? (
            noOccurrences
          ) : (
            <>
              <div className="pd-sec">
                <span className="lbl">What else was going on · {exceptions} against the pattern</span>
                {showSeg}
              </div>
              <ul className="ctx pd-card">
                {occ.map((o) => (
                  <li key={o.date} className={o.is_exception ? 'exc' : ''} title={o.is_exception ? 'Went against the pattern' : undefined}>
                    <div className="ctx-head">
                      <b>{when(o)}</b>
                      <span className="ctx-ev">{transitLabel(o.event)}</span>
                      <OutcomeTag outcome={o.outcome} />
                      <span className={retTone(o.forward_return)}>{ret(o.forward_return)}</span>
                    </div>
                    <div className="ctx-meta">
                      <span>
                        Regime {o.regime ?? <span className="dim">n/a</span>}
                        {o.regime && o.regime_scope === 'OWN' && <span className="dim"> (own)</span>}
                      </span>
                      <span title="20-day realised volatility vs this asset's own history">
                        Vol pct {o.volatility_percentile === null ? '—' : pct(o.volatility_percentile)}
                      </span>
                    </div>
                    <p className="ctx-note">
                      <span className="lbl">Also in the window</span>{' '}
                      {o.conflicting_events.length > 0 && <span className="warn">Conflicting: {o.conflicting_events.join('; ')}. </span>}
                      {o.concurrent_events.length > 0 ? <span className="mid">{o.concurrent_events.join(', ')}</span> : <span className="dim">—</span>}
                    </p>
                  </li>
                ))}
                {!occ.length && <li className="dim ctx-none">No occurrence went against the pattern.</li>}
              </ul>
              {lunarNote}
            </>
          ))}
      </div>
    </div>
  )
}
