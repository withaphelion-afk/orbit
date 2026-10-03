import { CalendarClock, CircleDot, Orbit, RotateCcw, Sigma, Sparkles, SunDim, WavesHorizontal } from 'lucide-react'
import { useState } from 'react'
import { usePlaybook, useSky, useTransits } from '../api/hooks'
import type { ConfidenceLabel, SkyPosition } from '../api/types'
import { Empty, Pill, QueryState, Seg, StatCard, StatGrid } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META } from '../config'
import { day, daysFrom, EVENT_KIND, hhmm, pct, pval, transitLabel } from '../lib/format'
import { useTerminal } from '../state/store'
import { ConfLabel, OutcomeTag } from './astro/labels'
import { ModelTab } from './astro/ModelTab'
import { ProjectionsTab } from './astro/ProjectionsTab'
import { PlaybookTab } from './astro/PlaybookTab'

type Tab = 'PROJECTIONS' | 'SKY' | 'EVENTS' | 'PLAYBOOK' | 'CHOP' | 'MODEL'
const TABS: Tab[] = ['PROJECTIONS', 'SKY', 'EVENTS', 'PLAYBOOK', 'CHOP', 'MODEL']
const ICON = { size: 18, strokeWidth: 1.75 } as const
const EVIDENCE: ConfidenceLabel[] = ['strong', 'moderate', 'weak']

export function AstroPanel({ hidden }: { hidden: boolean }) {
  const [tab, setTab] = useState<Tab>('PROJECTIONS')
  const asset = useTerminal((s) => s.asset)
  return (
    <Panel
      code="ASTRO"
      title={
        tab === 'PROJECTIONS' ? 'Projections: upcoming events and what history says' : tab === 'MODEL' ? `Vedic model · ${ASSET_META[asset].name}` : tab === 'PLAYBOOK' || tab === 'CHOP' ? `Transit research · ${ASSET_META[asset].name}` : 'Sky and transits (Vedic)'
      }
      description={
        <>
          Retrospective research, not a trading signal. Vedic rules throughout: sidereal zodiac (Lahiri / Chitrapaksha ayanamsa), the 9 grahas, rashi
          drishti, yogas. Patterns are only trusted once they survive multiple-testing correction, and nothing here sizes a trade. Positions come from
          NASA JPL's DE421 ephemeris.
        </>
      }
      hidden={hidden}
      tools={
        <>
          <Seg label="View" value={tab} onChange={setTab} options={TABS.map((t) => ({ label: t, value: t }))} />
          <Pill tone="astro" title="Research only: nothing on this screen is a trading signal">
            RESEARCH
          </Pill>
        </>
      }
    >
      {tab === 'PROJECTIONS' && <ProjectionsTab />}
      {tab === 'SKY' && <SkyTab />}
      {tab === 'EVENTS' && <EventsTab />}
      {tab === 'PLAYBOOK' && <PlaybookTab asset={asset} />}
      {tab === 'CHOP' && <ChopTab />}
      {tab === 'MODEL' && <ModelTab asset={asset} />}
    </Panel>
  )
}

const deg = (d: number) => `${Math.floor(d)}°${String(Math.floor((d % 1) * 60)).padStart(2, '0')}′`
const NODES = ['RAHU', 'KETU']

function SkyTab() {
  const { data, isPending, error } = useSky()
  if (!data) return <QueryState isPending={isPending} error={error} what="planet positions" />
  const vakri = data.filter((p) => p.retrograde && !NODES.includes(p.planet))
  const asta = data.filter((p) => p.combust)
  const soonest = data
    .filter((p) => p.next_event)
    .sort((a, b) => Date.parse(a.next_event!.exact_time ?? a.next_event!.date) - Date.parse(b.next_event!.exact_time ?? b.next_event!.date))[0]
  return (
    <div className="astro-tab">
      <p className="astro-intro">Where each graha sits in the sidereal zodiac right now, its state, and its next change.</p>
      <StatGrid>
        <StatCard
          icon={<RotateCcw {...ICON} />}
          label="Vakri now"
          value={vakri.length}
          tone={vakri.length ? 'warn' : undefined}
          caption={vakri.length ? vakri.map((p) => p.name.split(' (')[0]).join(', ') : 'none retrograde (Rahu and Ketu always are)'}
          title="Retrograde grahas, not counting Rahu and Ketu, which always move vakri"
        />
        <StatCard
          icon={<SunDim {...ICON} />}
          label="Asta now"
          value={asta.length}
          tone={asta.length ? 'warn' : undefined}
          caption={asta.length ? asta.map((p) => p.name.split(' (')[0]).join(', ') : 'none combust'}
          title="Grahas combust (too close to the Sun)"
        />
        <StatCard
          icon={<CalendarClock {...ICON} />}
          label="Next change"
          value={soonest ? daysFrom(soonest.next_event!.date) : '—'}
          tone="astro"
          caption={soonest ? transitLabel(soonest.next_event!) : 'no upcoming change listed'}
        />
      </StatGrid>
      <div className="tbl-wrap astro-card">
        <table className="tbl sky">
          <thead>
            <tr>
              <th className="l">Graha</th>
              <th className="l">Rashi</th>
              <th>Degree</th>
              <th className="l">Nakshatra · pada</th>
              <th className="l">State</th>
              <th className="l">Next change</th>
              <th className="l">When</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p: SkyPosition) => (
              <tr key={p.planet}>
                <td className="l body">{p.name}</td>
                <td className="l">{p.sign}</td>
                <td>{deg(p.degree)}</td>
                <td className="l">
                  {p.nakshatra} · {p.pada}
                </td>
                <td className="l">
                  {[
                    p.retrograde ? (
                      <span key="v" className="warn">
                        {NODES.includes(p.planet) ? 'vakri (always)' : 'VAKRI'}
                      </span>
                    ) : (
                      <span key="m" className="dim">
                        margi
                      </span>
                    ),
                    p.combust && (
                      <span key="a" className="warn">
                        {' '}
                        · ASTA
                      </span>
                    ),
                    p.dignity && (
                      <span key="d" className="hi">
                        {' '}
                        · {p.dignity.toUpperCase()}
                      </span>
                    ),
                  ]}
                </td>
                <td className="l">{p.next_event ? transitLabel(p.next_event) : '—'}</td>
                <td className="l mid">
                  {p.next_event ? `${day(p.next_event.exact_time ?? p.next_event.date)} ${p.next_event.exact_time ? hhmm(p.next_event.exact_time) : ''} · ${daysFrom(p.next_event.date)}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EventsTab() {
  const { data, isPending, error } = useTransits()
  if (!data) return <QueryState isPending={isPending} error={error} what="transits" />
  const today = new Date().toISOString().slice(0, 10)
  const next = data.find((v) => v.event.date.slice(0, 10) >= today)
  const upcoming = data.filter((v) => v.event.date.slice(0, 10) >= today)
  const notable = upcoming.filter((v) => v.notable.length > 0)
  return (
    <div className="astro-tab">
      <p className="astro-intro">
        Recent and upcoming transits; the next one is highlighted. "Notable for" lists the assets whose playbook rates that pattern weak or better.
      </p>
      <StatGrid>
        <StatCard
          icon={<Orbit {...ICON} />}
          label="Next transit"
          value={next ? daysFrom(next.event.date) : '—'}
          tone="astro"
          caption={next ? `${transitLabel(next.event)} · ${day(next.event.date)}` : 'none listed ahead'}
        />
        <StatCard icon={<CalendarClock {...ICON} />} label="Upcoming" value={upcoming.length} caption={`of ${data.length} transits listed`} />
        <StatCard
          icon={<Sparkles {...ICON} />}
          label="Notable ahead"
          value={notable.length}
          tone={notable.length ? undefined : 'dim'}
          caption="upcoming transits some asset's playbook rates weak or better"
        />
      </StatGrid>
      <div className="tbl-wrap astro-card">
        <table className="tbl tl">
          <thead>
            <tr>
              <th className="l">Date</th>
              <th className="l">When</th>
              <th className="l">Exact (UTC)</th>
              <th className="l">Transit</th>
              <th className="l">Type</th>
              <th className="l" title="Assets whose playbook rates this pattern weak or better">
                Notable for
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((v) => (
              <tr
                key={`${v.event.planet}-${v.event.other_planet}-${v.event.event_type}-${v.event.to_state}-${v.event.exact_time ?? v.event.date}`}
                className={`${v.event.date.slice(0, 10) < today ? 'past' : ''} ${v === next ? 'next' : ''}`}
              >
                <td className="l">
                  {day(v.event.date)} {new Date(v.event.date).getUTCFullYear()}
                </td>
                <td className="l">{daysFrom(v.event.date)}</td>
                <td className="l mid">{v.event.exact_time ? `${day(v.event.exact_time)} ${hhmm(v.event.exact_time)}` : '—'}</td>
                <td className="l body">{transitLabel(v.event)}</td>
                <td className="l dim">{EVENT_KIND[v.event.event_type] ?? v.event.event_type}</td>
                <td className="l">
                  {v.notable.length ? (
                    <span className="notables">
                      {v.notable.map((n) => (
                        <span key={n.asset} className="notable">
                          {ASSET_META[n.asset].label} <ConfLabel label={n.label} /> <OutcomeTag outcome={n.dominant_outcome} />
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="dim">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ChopTab() {
  const asset = useTerminal((s) => s.asset)
  const { data, isPending, error } = usePlaybook(asset)
  const [showAll, setShowAll] = useState(false)
  if (!data) return <QueryState isPending={isPending} error={error} what="the chop track" />
  const rows = showAll ? data.sideways : data.sideways.filter((s) => s.label !== 'insufficient_data')
  const tested = data.sideways.filter((s) => s.label !== 'insufficient_data').length
  const evidence = data.sideways.filter((s) => EVIDENCE.includes(s.label)).length
  return (
    <div className="astro-tab">
      <p className="astro-intro">
        Which Vedic states (vakri, asta, rashi placements, yogas…) coincide with sideways markets. The honest sample is the number of separate episodes of a state, not its
        day count.
      </p>
      <StatGrid>
        <StatCard icon={<Sigma {...ICON} />} label="Tested" value={tested} caption={`state × horizon pairs with enough episodes, of ${data.sideways.length}`} />
        <StatCard
          icon={<WavesHorizontal {...ICON} />}
          label="With evidence"
          value={evidence}
          tone={evidence ? undefined : 'dim'}
          caption="rated STRONG, MODERATE or WEAK"
        />
        <StatCard icon={<CircleDot {...ICON} />} label="Too few" value={data.sideways.length - tested} tone="dim" caption="too few episodes to test" />
      </StatGrid>
      <div className="astro-bar">
        <Seg
          label="Show"
          value={showAll ? 'ALL' : 'TESTED'}
          onChange={(v) => setShowAll(v === 'ALL')}
          options={[
            { label: 'TESTED', value: 'TESTED' },
            { label: 'ALL', value: 'ALL' },
          ]}
        />
        <span className="dim">{rows.length} rows</span>
      </div>
      {rows.length === 0 ? (
        <Empty title="NOTHING TESTED">
          <span>No transit state has enough separate episodes in this asset's history to be tested.</span>
        </Empty>
      ) : (
        <div className="tbl-wrap astro-card">
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
    </div>
  )
}
