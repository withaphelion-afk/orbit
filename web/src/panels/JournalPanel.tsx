import { useMemo, useState } from 'react'
import {
  ArrowDownRight,
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  ChevronUp,
  ChevronsUpDown,
  Hourglass,
  ListChecks,
  SearchX,
  SkipForward,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { useComponents, useJournal } from '../api/hooks'
import type { JournalRow } from '../api/types'
import { NotBuilt, QueryState, Seg, StatCard, StatGrid } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, num, price, signed, tone } from '../lib/format'

type Filter = 'ALL' | 'TAKEN' | 'SKIPPED' | 'MODIFIED' | 'EXPIRED' | 'OPEN'
type SortKey = 'date' | 'asset' | 'conf' | 'pnl'
type TfFilter = 'ALL' | '4h' | '1d'

const FILTERS: Filter[] = ['ALL', 'TAKEN', 'SKIPPED', 'MODIFIED', 'EXPIRED', 'OPEN']
const NO_ROWS: JournalRow[] = []
const ICON = { size: 18, strokeWidth: 1.75 }
const isOpen = (r: JournalRow) => r.entry.decision !== 'SKIPPED' && r.entry.outcome_pnl === null
const statTone = (v: number) => (v > 0 ? 'up' : v < 0 ? 'down' : 'dim')

const sortValue: Record<SortKey, (r: JournalRow) => number | string> = {
  date: (r) => r.decided_at,
  asset: (r) => r.entry.suggestion.asset,
  conf: (r) => r.entry.suggestion.confidence,
  pnl: (r) => r.entry.outcome_pnl ?? -Infinity,
}

export function JournalPanel({ hidden }: { hidden: boolean }) {
  const { components, error: sysError, isPending: sysPending } = useComponents()
  const built = !!components?.journal
  const journal = useJournal(built)
  const data = journal.data ?? NO_ROWS
  const [filter, setFilter] = useState<Filter>('ALL')
  const [tfFilter, setTfFilter] = useState<TfFilter>('ALL')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'date', dir: -1 })

  const stats = useMemo(() => {
    const acted = data.filter((r) => r.entry.decision !== 'SKIPPED')
    const closed = acted.filter((r) => r.entry.outcome_pnl !== null)
    const wins = closed.filter((r) => (r.entry.outcome_pnl ?? 0) > 0).length
    const pnl = closed.reduce((s, r) => s + (r.entry.outcome_pnl ?? 0), 0)
    const skippedPnl = data.reduce((s, r) => s + (r.counterfactual_pnl ?? 0), 0)
    return {
      acted: acted.length,
      open: acted.length - closed.length,
      closed: closed.length,
      winRate: closed.length ? (wins / closed.length) * 100 : null,
      pnl,
      skippedPnl,
    }
  }, [data])

  const rows = useMemo(() => {
    const f = data.filter((r) =>
      (tfFilter === 'ALL' || (r.timeframe ?? '1d') === tfFilter) &&
      (filter === 'ALL' ? true : filter === 'OPEN' ? isOpen(r) : filter === 'EXPIRED' ? r.expired : r.entry.decision === filter && !r.expired),
    )
    const get = sortValue[sort.key]
    return f.slice().sort((a, b) => (get(a) > get(b) ? 1 : get(a) < get(b) ? -1 : 0) * sort.dir)
  }, [data, filter, sort, tfFilter])

  const th = (key: SortKey, label: string, cls = '', title = `Sort by ${label}`) => {
    const on = sort.key === key
    const Arrow = !on ? ChevronsUpDown : sort.dir > 0 ? ChevronUp : ChevronDown
    return (
      <th className={`sort ${cls}`} aria-sort={on ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'} title={title}>
        <button type="button" className={`jr-sort ${on ? 'on' : ''}`} onClick={() => setSort({ key, dir: on ? (-sort.dir as 1 | -1) : -1 })}>
          {label}
          <Arrow className="ar" size={12} strokeWidth={2} aria-hidden="true" />
        </button>
      </th>
    )
  }

  const loaded = built && journal.data !== undefined

  return (
    <Panel
      code="JRNL"
      title="Trade journal"
      description="Every suggestion you took, skipped or modified, plus the ones that expired undecided, and how each one turned out."
      hidden={hidden}
      tools={
        <>
          <Seg label="Filter" value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ label: f, value: f }))} />
          <Seg
            label="Timeframe"
            value={tfFilter}
            onChange={setTfFilter}
            options={[
              { label: 'ALL TF', value: 'ALL' as TfFilter },
              { label: '4H', value: '4h' as TfFilter },
              { label: '1D', value: '1d' as TfFilter },
            ]}
          />
          {loaded && (
            <span className="jr-count">
              {filter === 'ALL' ? `${data.length} ${data.length === 1 ? 'entry' : 'entries'}` : `${rows.length} of ${data.length}`}
            </span>
          )}
        </>
      }
    >
      {!components ? (
        <QueryState isPending={sysPending} error={sysError} what="system status" />
      ) : !built ? (
        <NotBuilt layer="JOURNAL">
          <span>This backend doesn't report a journal. Update it to the latest code.</span>
        </NotBuilt>
      ) : (
        <div className="jr">
          {journal.isError && <QueryState isPending={false} error={journal.error} what="the journal" />}
          {!loaded ? (
            !journal.isError && <QueryState isPending error={null} what="the journal" />
          ) : (
            <>
              <StatGrid>
                <StatCard label="Acted" value={stats.acted} caption="taken or modified" icon={<ListChecks {...ICON} />} />
                <StatCard label="Open" value={stats.open} caption="no outcome yet" icon={<Hourglass {...ICON} />} />
                <StatCard
                  label="Win rate"
                  value={stats.winRate === null ? '—' : `${num(stats.winRate, 0)}%`}
                  tone={stats.winRate === null ? 'dim' : undefined}
                  caption={stats.closed ? `of ${stats.closed} closed` : 'none closed yet'}
                  icon={<Target {...ICON} />}
                />
                <StatCard
                  label="Closed P&L"
                  value={`${signed(stats.pnl)}%`}
                  tone={statTone(stats.pnl)}
                  caption="sum of closed returns"
                  icon={stats.pnl < 0 ? <TrendingDown {...ICON} /> : <TrendingUp {...ICON} />}
                />
                <StatCard
                  label="Skipped would-be"
                  value={`${signed(stats.skippedPnl)}%`}
                  tone={statTone(stats.skippedPnl)}
                  caption="skipped and expired"
                  title="What the skipped and expired suggestions would have returned, with the strategy's own levels"
                  icon={<SkipForward {...ICON} />}
                />
              </StatGrid>

              <div className="jr-card">
                {rows.length ? (
                  <table className="tbl jr-tbl">
                    <thead>
                      <tr>
                        {th('date', 'Date', 'l')}
                        {th('asset', 'Asset', 'l')}
                        <th className="l" title="The bars the suggestion lived on">TF</th>
                        <th className="l">Dir</th>
                        <th className="l">Decision</th>
                        <th className="l" title="Why the position closed: target, stop or time">
                          Exit
                        </th>
                        {th('conf', 'Conf')}
                        <th>Entry</th>
                        <th>Stop</th>
                        <th>Target</th>
                        {th('pnl', 'P&L %', '', "Sort by P&L. In brackets: what a skipped or expired suggestion would have returned")}
                        <th className="l">Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const s = r.entry.suggestion
                        const pnl = r.entry.outcome_pnl
                        const decision = r.expired ? 'EXPIRED' : r.entry.decision
                        return (
                          <tr key={r.id} className={r.expired ? 'expired' : undefined}>
                            <td className="l mid">{day(r.decided_at)}</td>
                            <td className="l strong">{ASSET_META[s.asset].label}</td>
                            <td className="l mid">{(r.timeframe ?? '1d').toUpperCase()}</td>
                            <td className={`l ${s.direction === 'LONG' ? 'up' : 'down'}`}>
                              <span className="jr-dir">
                                {s.direction === 'LONG' ? <ArrowUpRight size={14} strokeWidth={2} aria-hidden="true" /> : <ArrowDownRight size={14} strokeWidth={2} aria-hidden="true" />}
                                {s.direction}
                              </span>
                            </td>
                            <td className="l">
                              <span className={`dec ${decision}`}>{decision}</span>
                            </td>
                            <td className="l mid jr-exit">{r.exit_reason ?? '—'}</td>
                            <td>{s.confidence.toFixed(2)}</td>
                            <td>{price(s.asset, s.entry_price)}</td>
                            <td className="mid">{price(s.asset, s.stop_loss)}</td>
                            <td className="mid">{price(s.asset, s.take_profit)}</td>
                            <td>
                              {pnl !== null ? (
                                <span className={tone(pnl)}>{signed(pnl)}</span>
                              ) : r.counterfactual_pnl !== null ? (
                                <span className="shadow" title="Would have returned">
                                  ({signed(r.counterfactual_pnl)})
                                </span>
                              ) : r.entry.decision === 'SKIPPED' ? (
                                <span className="dim">—</span>
                              ) : (
                                <span className="jr-open">OPEN</span>
                              )}
                            </td>
                            <td className="l note">{r.entry.notes || <span className="dim">—</span>}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                ) : data.length ? (
                  <div className="empty jr-empty">
                    <SearchX className="jr-empty-ico" {...ICON} aria-hidden="true" />
                    <b>NO MATCHES</b>
                    <span>No entries match {filter}.</span>
                    <button type="button" className="act skip" onClick={() => setFilter('ALL')}>
                      Show all {data.length}
                    </button>
                  </div>
                ) : (
                  <div className="empty jr-empty">
                    <BookOpen className="jr-empty-ico" {...ICON} aria-hidden="true" />
                    <b>NOTHING LOGGED YET</b>
                    <span>Decide on a suggestion in SUGG (F4); undecided ones land here when they expire.</span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </Panel>
  )
}
