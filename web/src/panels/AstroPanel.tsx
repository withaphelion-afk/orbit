import { useState } from 'react'
import { usePlaybook, useSky, useTransits } from '../api/hooks'
import type { SkyPosition } from '../api/types'
import { Empty, Pill, QueryState, Seg } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, daysFrom, pct, pval, transitLabel } from '../lib/format'
import { useTerminal } from '../state/store'
import { ConfLabel, OutcomeTag } from './astro/labels'
import { PlaybookTab } from './astro/PlaybookTab'

type Tab = 'SKY' | 'EVENTS' | 'PLAYBOOK' | 'CHOP'
const TABS: Tab[] = ['SKY', 'EVENTS', 'PLAYBOOK', 'CHOP']

export function AstroPanel({ hidden }: { hidden: boolean }) {
  const [tab, setTab] = useState<Tab>('PLAYBOOK')
  const asset = useTerminal((s) => s.asset)
  return (
    <Panel
      code="ASTRO"
      title={tab === 'PLAYBOOK' || tab === 'CHOP' ? `Transit research · ${ASSET_META[asset].name}` : 'Sky and transits'}
      hidden={hidden}
      meta={
        <>
          <Pill tone="astro">RESEARCH</Pill>
          <Seg label="View" value={tab} onChange={setTab} options={TABS.map((t) => ({ label: t, value: t }))} />
        </>
      }
    >
      <div className="astro-banner">
        <span>
          Retrospective research, not a trading signal. Transit patterns are only trusted once they survive multiple-testing correction, and
          nothing here sizes a trade. Positions come from NASA JPL's DE421 ephemeris.
        </span>
      </div>
      {tab === 'SKY' && <SkyTab />}
      {tab === 'EVENTS' && <EventsTab />}
      {tab === 'PLAYBOOK' && <PlaybookTab asset={asset} />}
      {tab === 'CHOP' && <ChopTab />}
    </Panel>
  )
}

const deg = (d: number) => `${Math.floor(d)}°${String(Math.floor((d % 1) * 60)).padStart(2, '0')}′`

function SkyTab() {
  const { data, isPending, error } = useSky()
  if (!data) return <QueryState isPending={isPending} error={error} what="planet positions" />
  return (
    <div className="tbl-wrap">
      <table className="tbl sky">
        <thead>
          <tr>
            <th className="l">Body</th>
            <th className="l">Sign</th>
            <th>Degree</th>
            <th className="l">Motion</th>
            <th className="l">Next transit</th>
            <th className="l">When</th>
          </tr>
        </thead>
        <tbody>
          {data.map((p: SkyPosition) => (
            <tr key={p.planet}>
              <td className="l body">{p.planet}</td>
              <td className="l">{p.sign}</td>
              <td>{deg(p.degree)}</td>
              <td className="l">{p.retrograde ? <span className="warn">RETROGRADE</span> : <span className="dim">direct</span>}</td>
              <td className="l">{p.next_event ? transitLabel(p.next_event) : '—'}</td>
              <td className="l">{p.next_event ? `${day(p.next_event.date)} · ${daysFrom(p.next_event.date)}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EventsTab() {
  const { data, isPending, error } = useTransits()
  if (!data) return <QueryState isPending={isPending} error={error} what="transits" />
  const today = new Date().toISOString().slice(0, 10)
  const next = data.find((v) => v.event.date.slice(0, 10) >= today)
  return (
    <div className="tbl-wrap">
      <table className="tbl tl">
        <thead>
          <tr>
            <th className="l">Date</th>
            <th className="l">When</th>
            <th className="l">Transit</th>
            <th className="l">Type</th>
            <th className="l" title="Assets whose playbook rates this pattern weak or better">Notable for</th>
          </tr>
        </thead>
        <tbody>
          {data.map((v) => (
            <tr key={`${v.event.planet}-${v.event.event_type}-${v.event.date}`} className={`${v.event.date.slice(0, 10) < today ? 'past' : ''} ${v === next ? 'next' : ''}`}>
              <td className="l">
                {day(v.event.date)} {new Date(v.event.date).getUTCFullYear()}
              </td>
              <td className="l">{daysFrom(v.event.date)}</td>
              <td className="l body">{transitLabel(v.event)}</td>
              <td className="l dim">{v.event.event_type === 'INGRESS' ? 'ingress' : 'station'}</td>
              <td className="l">
                {v.notable.length ? (
                  v.notable.map((n) => (
                    <span key={n.asset} className="notable">
                      {ASSET_META[n.asset].label} <ConfLabel label={n.label} /> <OutcomeTag outcome={n.dominant_outcome} />
                    </span>
                  ))
                ) : (
                  <span className="dim">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ChopTab() {
  const asset = useTerminal((s) => s.asset)
  const { data, isPending, error } = usePlaybook(asset)
  const [showAll, setShowAll] = useState(false)
  if (!data) return <QueryState isPending={isPending} error={error} what="the chop track" />
  const rows = showAll ? data.sideways : data.sideways.filter((s) => s.label !== 'insufficient_data')
  return (
    <>
      <div className="pbk-tools">
        <span className="dim">
          Which transit states coincide with sideways markets. The honest sample is the number of separate episodes of a state, not its day count.
        </span>
        <Seg
          label="Show"
          value={showAll ? 'ALL' : 'TESTED'}
          onChange={(v) => setShowAll(v === 'ALL')}
          options={[
            { label: 'TESTED', value: 'TESTED' },
            { label: 'ALL', value: 'ALL' },
          ]}
        />
      </div>
      {rows.length === 0 ? (
        <Empty title="NOTHING TESTED">
          <span>No transit state has enough separate episodes in this asset's history to be tested.</span>
        </Empty>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th className="l">Label</th>
                <th className="l">State</th>
                <th>Horizon</th>
                <th>Episodes</th>
                <th>Days</th>
                <th>Chop rate · base</th>
                <th>p</th>
                <th>q</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={`${s.state_id}-${s.horizon_days}`}>
                  <td className="l">
                    <ConfLabel label={s.label} />
                  </td>
                  <td className="l">{s.description}</td>
                  <td>{s.horizon_days}d</td>
                  <td>{s.episodes}</td>
                  <td>{s.days_in_state}</td>
                  <td>
                    {pct(s.sideways_rate_in_state)} · <span className="dim">{pct(s.base_sideways_rate)}</span>
                  </td>
                  <td>{pval(s.p_value)}</td>
                  <td>{pval(s.q_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
