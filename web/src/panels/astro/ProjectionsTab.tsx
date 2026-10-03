import { CalendarClock, ChevronRight, ShieldAlert, ShieldCheck, Target } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useProjections, useProjectionTrack } from '../../api/hooks'
import type { Asset, ConfidenceLabel, ProjectionView } from '../../api/types'
import { Empty, QueryState, Seg, StatCard, StatGrid } from '../../components/bits'
import { ASSETS, ASSET_META } from '../../config'
import { day, hhmm, num, pct, pval, signed, tone } from '../../lib/format'
import { useNow } from '../../hooks/useLiveFeed'
import { ConfLabel, OutcomeTag } from './labels'
import { PatternDetail } from './PlaybookTab'

const ICON = { size: 18, strokeWidth: 1.75 } as const
const RANK: Record<ConfidenceLabel, number> = { strong: 4, moderate: 3, weak: 2, none: 1, insufficient_data: 0 }
type AssetFilter = 'ALL' | Asset
type SortKey = 'date' | 'odds' | 'reliability'
const DAYS = [7, 30, 90]

/** "in 2d 4h" / "now" / "3h ago" */
function countdown(iso: string, now: number) {
  const ms = Date.parse(iso) - now
  const abs = Math.abs(ms)
  const d = Math.floor(abs / 86_400_000)
  const h = Math.floor((abs % 86_400_000) / 3_600_000)
  const m = Math.floor((abs % 3_600_000) / 60_000)
  const span = d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`
  return ms >= 0 ? `in ${span}` : `${span} ago`
}

const projectionText = (p: ProjectionView) => {
  const what = p.outcome === 'BIG_UP' ? 'Big ↑' : p.outcome === 'BIG_DOWN' ? 'Big ↓' : p.outcome === 'SIDEWAYS' ? 'Sideways' : 'Nothing special'
  return `${what} within ${p.horizon_days} ${p.horizon_days === 1 ? 'day' : 'days'}`
}

/** Upcoming Vedic events per asset, each with what the playbook says followed it before, and how reliable that is. */
export function ProjectionsTab() {
  const [asset, setAsset] = useState<AssetFilter>('ALL')
  const [days, setDays] = useState(30)
  const [showNone, setShowNone] = useState(false)
  const [sort, setSort] = useState<SortKey>('date')
  const [selected, setSelected] = useState<string | null>(null)
  const { data, isPending, error } = useProjections(days, showNone)
  const track = useProjectionTrack()
  const now = useNow(60_000)

  const rows = useMemo(() => {
    const list = (data ?? []).filter((p) => asset === 'ALL' || p.asset === asset)
    const by: Record<SortKey, (p: ProjectionView) => number> = {
      date: (p) => Date.parse(p.window_start),
      odds: (p) => -(p.lift ?? 0),
      reliability: (p) => -(RANK[p.label] * 1000 + p.score),
    }
    return list.slice().sort((a, b) => by[sort](a) - by[sort](b))
  }, [data, asset, sort])

  if (!data) return <QueryState isPending={isPending} error={error} what="projections" />
  const current = rows.find((p) => p.id === selected) ?? rows[0]
  const trusted = rows.filter((p) => p.trusted).length
  const t = track.data

  return (
    <div className="astro-tab">
      <p className="astro-intro">
        Every Vedic event coming up, per asset, with what followed it in the past. Only STRONG or MODERATE patterns are trusted; everything else is
        shown as unproven history, not a forecast.
      </p>
      <StatGrid>
        <StatCard icon={<CalendarClock {...ICON} />} label="Upcoming" value={rows.length} caption={`event × asset rows in the next ${days} days`} />
        <StatCard
          icon={trusted ? <ShieldCheck {...ICON} /> : <ShieldAlert {...ICON} />}
          label="Trusted"
          value={trusted}
          tone={trusted ? 'up' : 'dim'}
          caption={trusted ? 'pass multiple-testing correction' : 'none pass correction: all unproven'}
        />
        <StatCard
          icon={<Target {...ICON} />}
          label="Track record"
          value={t?.total.hit_rate == null ? '—' : pct(t.total.hit_rate)}
          caption={
            t
              ? t.total.graded
                ? `${t.total.hits}/${t.total.graded} hit after publishing · chance ${t.total.avg_base_rate == null ? '—' : pct(t.total.avg_base_rate)}`
                : `${t.total.recorded} logged, none graded yet`
              : 'loading'
          }
        />
      </StatGrid>
      <div className="pbk-body">
        <div className="pbk-list">
          <div className="pbk-tools">
            <Seg
              label="Asset"
              value={asset}
              onChange={setAsset}
              options={[{ label: 'ALL', value: 'ALL' as AssetFilter }, ...ASSETS.map((a) => ({ label: ASSET_META[a].label, value: a as AssetFilter }))]}
            />
            <Seg label="Days ahead" value={String(days)} onChange={(v) => setDays(Number(v))} options={DAYS.map((d) => ({ label: `${d}D`, value: String(d) }))} />
            <Seg
              label="Sort"
              value={sort}
              onChange={setSort}
              options={[
                { label: 'DATE', value: 'date' as SortKey },
                { label: 'ODDS', value: 'odds' as SortKey },
                { label: 'RELIABILITY', value: 'reliability' as SortKey },
              ]}
            />
            <label className="chk" title="NONE-rated patterns showed no difference from normal">
              <input type="checkbox" checked={showNone} onChange={(e) => setShowNone(e.target.checked)} /> Show NONE
            </label>
          </div>
          {!rows.length ? (
            <Empty title="NOTHING COMING UP">
              <span>No upcoming event has a tested pattern for {asset === 'ALL' ? 'any asset' : ASSET_META[asset].label} in the next {days} days.</span>
            </Empty>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl pbk-tbl">
                <thead>
                  <tr>
                    <th className="l">When (UTC)</th>
                    <th className="l">Event · asset</th>
                    <th className="l">Projection</th>
                    <th title="Rate after the event vs normal, with the 95% range">Odds</th>
                    <th title="Average return and win rate at that horizon">Size</th>
                    <th className="l">Reliability</th>
                    <th aria-hidden />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id} className={`click ${p === current ? 'sel' : ''}`} onClick={() => setSelected(p.id)}>
                      <td className="l mid">
                        {day(p.window_start)} {hhmm(p.window_start)}
                        <div className="pbk-sub">{countdown(p.window_start, now)}</div>
                      </td>
                      <td className="l pbk-pat">
                        <span className="pbk-name">{p.event.label || p.description}</span>
                        <span className="pbk-sub">
                          {ASSET_META[p.asset].label}
                          {p.conflict && <span className="warn"> · conflicting signals in this window</span>}
                        </span>
                      </td>
                      <td className="l">
                        <OutcomeTag outcome={p.outcome} /> <span className="dim">{projectionText(p)}</span>
                      </td>
                      <td>
                        {pct(p.hit_rate)} <span className="dim">vs {pct(p.base_rate)}</span>
                        <div className="pbk-sub">{p.lift == null ? '' : `${num(p.lift, 1)}× · ${pct(p.ci_low)}–${pct(p.ci_high)}`}</div>
                      </td>
                      <td className={tone(p.mean_return)}>
                        {signed(p.mean_return * 100, 1)}%<div className="pbk-sub">win {pct(p.win_rate)}</div>
                      </td>
                      <td className="l">
                        <ConfLabel label={p.label} /> <span className="dim">N {p.n} · q {pval(p.q_value)}</span>
                        {!p.trusted && <div className="pbk-sub">unproven, not significant</div>}
                      </td>
                      <td className="chev">
                        <ChevronRight size={15} strokeWidth={1.75} aria-hidden />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="pbk-detail">{current ? <ProjectionEvidence p={current} /> : null}</div>
      </div>
    </div>
  )
}

/** How the projection was calculated, how it looks in conditions like now, then the pattern's full evidence. */
function ProjectionEvidence({ p }: { p: ProjectionView }) {
  return (
    <div className="proj-evidence">
      <div className={`proj-verdict ${p.trusted ? 'up' : 'warn'}`}>{p.trusted ? 'Trusted: survives multiple-testing correction.' : 'Unproven, not significant.'}</div>
      <p className="dim">{p.note}</p>
      <table className="tbl">
        <tbody>
          <tr>
            <td className="l">Window</td>
            <td>
              {day(p.window_start)} {hhmm(p.window_start)} → {day(p.window_end)}
            </td>
          </tr>
          <tr>
            <td className="l">Normal rate (every day)</td>
            <td>{pct(p.base_rate)}</td>
          </tr>
          <tr>
            <td className="l">Rate after this event</td>
            <td>
              {pct(p.hit_rate)} ({pct(p.ci_low)}–{pct(p.ci_high)}, N {p.n})
            </td>
          </tr>
          <tr>
            <td className="l">Corrected q</td>
            <td>{pval(p.q_value)}</td>
          </tr>
          <tr>
            <td className="l">Hourly timing</td>
            <td>
              <ConfLabel label={p.timing_label} />
              {p.median_hours_to_move != null && <span className="dim"> · move starts ~{num(p.median_hours_to_move, 0)}h after</span>}
            </td>
          </tr>
          <tr>
            <td className="l">In conditions like now</td>
            <td>
              {p.like_now
                ? `${p.like_now.matches}/${p.like_now.n} (${pct(p.like_now.share)}) in a ${p.like_now.regime} regime at similar volatility`
                : 'no comparable past occurrences'}
            </td>
          </tr>
        </tbody>
      </table>
      <PatternDetail asset={p.asset} id={p.pattern_id} />
    </div>
  )
}
