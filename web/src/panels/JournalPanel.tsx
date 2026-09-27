import { useMemo, useState } from 'react'
import { useComponents, useJournal } from '../api/hooks'
import type { JournalRow } from '../api/types'
import { NotBuilt, QueryState, Seg } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, num, price, signed, tone } from '../lib/format'

type Filter = 'ALL' | 'TAKEN' | 'SKIPPED' | 'MODIFIED' | 'OPEN'
type SortKey = 'date' | 'asset' | 'conf' | 'pnl'

const FILTERS: Filter[] = ['ALL', 'TAKEN', 'SKIPPED', 'MODIFIED', 'OPEN']
const isOpen = (r: JournalRow) => r.entry.decision !== 'SKIPPED' && r.entry.outcome_pnl === null

const sortValue: Record<SortKey, (r: JournalRow) => number | string> = {
  date: (r) => r.decided_at,
  asset: (r) => r.entry.suggestion.asset,
  conf: (r) => r.entry.suggestion.confidence,
  pnl: (r) => r.entry.outcome_pnl ?? -Infinity,
}

export function JournalPanel({ hidden }: { hidden: boolean }) {
  const { components, error: sysError, isPending: sysPending } = useComponents()
  const built = !!components?.journal
  const { data = [], isError, error } = useJournal(built)
  const [filter, setFilter] = useState<Filter>('ALL')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'date', dir: -1 })

  const stats = useMemo(() => {
    const acted = data.filter((r) => r.entry.decision !== 'SKIPPED')
    const closed = acted.filter((r) => r.entry.outcome_pnl !== null)
    const wins = closed.filter((r) => (r.entry.outcome_pnl ?? 0) > 0).length
    const pnl = closed.reduce((s, r) => s + (r.entry.outcome_pnl ?? 0), 0)
    const skippedPnl = data.reduce((s, r) => s + (r.counterfactual_pnl ?? 0), 0)
    return { acted: acted.length, open: acted.length - closed.length, winRate: closed.length ? (wins / closed.length) * 100 : null, pnl, skippedPnl }
  }, [data])

  const rows = useMemo(() => {
    const f = data.filter((r) => (filter === 'ALL' ? true : filter === 'OPEN' ? isOpen(r) : r.entry.decision === filter))
    const get = sortValue[sort.key]
    return f.slice().sort((a, b) => (get(a) > get(b) ? 1 : get(a) < get(b) ? -1 : 0) * sort.dir)
  }, [data, filter, sort])

  const th = (key: SortKey, label: string, cls = '') => (
    <th className={`sort ${cls}`} onClick={() => setSort({ key, dir: sort.key === key ? (-sort.dir as 1 | -1) : -1 })} aria-sort={sort.key === key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
      {label}
      {sort.key === key && <span className="ar">{sort.dir > 0 ? ' ▲' : ' ▼'}</span>}
    </th>
  )

  return (
    <Panel code="JRNL" title="Trade journal" hidden={hidden} meta={<Seg label="Filter" value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ label: f, value: f }))} />}>
      {!components ? (
        <QueryState isPending={sysPending} error={sysError} what="system status" />
      ) : !built ? (
        <NotBuilt layer="JOURNAL">
          <span>
            The journal records every suggestion, what you decided and how it played out. It needs the strategy layer to produce suggestions
            first, and <code>src/orbit/journal/</code> is still empty.
          </span>
        </NotBuilt>
      ) : (
      <>
      {isError && <QueryState isPending={false} error={error} what="the journal" />}
      <div className="jbar">
        <div>
          <span className="lbl">Acted</span>
          <span className="v">{stats.acted}</span>
        </div>
        <div>
          <span className="lbl">Open</span>
          <span className="v hi">{stats.open}</span>
        </div>
        <div>
          <span className="lbl">Win rate</span>
          <span className="v">{stats.winRate === null ? '—' : `${num(stats.winRate, 0)}%`}</span>
        </div>
        <div>
          <span className="lbl">Closed P&amp;L</span>
          <span className={`v ${tone(stats.pnl)}`}>{signed(stats.pnl)}%</span>
        </div>
        <div title="What the skipped suggestions would have returned">
          <span className="lbl">Skipped would-be</span>
          <span className={`v ${tone(stats.skippedPnl)}`}>{signed(stats.skippedPnl)}%</span>
        </div>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              {th('date', 'Date', 'l')}
              {th('asset', 'Asset', 'l')}
              <th className="l">Dir</th>
              <th className="l">Decision</th>
              {th('conf', 'Conf')}
              <th>Entry</th>
              <th>Stop</th>
              <th>Target</th>
              {th('pnl', 'P&L %')}
              <th className="l">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const s = r.entry.suggestion
              const pnl = r.entry.outcome_pnl
              return (
                <tr key={r.id}>
                  <td className="l mid">{day(r.decided_at)}</td>
                  <td className="l strong">{ASSET_META[s.asset].label}</td>
                  <td className={`l ${s.direction === 'LONG' ? 'up' : 'down'}`}>{s.direction}</td>
                  <td className="l">
                    <span className={`dec ${r.entry.decision}`}>{r.entry.decision}</span>
                  </td>
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
                      <span className="hi">OPEN</span>
                    )}
                  </td>
                  <td className="l note">{r.entry.notes || <span className="dim">—</span>}</td>
                </tr>
              )
            })}
            {!rows.length && (
              <tr>
                <td colSpan={10} className="l dim empty-row">
                  No entries match {filter}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </>
      )}
    </Panel>
  )
}
