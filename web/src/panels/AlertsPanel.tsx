import { ArrowDownRight, ArrowUpRight, BellRing, Check, ShieldAlert, ShieldCheck, X } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { useAlerts, useDivergenceModel, useLabelDivergence } from '../api/hooks'
import type { AlertItem, Timeframe } from '../api/types'
import { Empty, Pill, QueryState, StatCard, StatGrid } from '../components/bits'
import { Panel } from '../components/Panel'
import { ASSET_META, type TvInterval } from '../config'
import { ago, pct, price } from '../lib/format'
import { useTerminal } from '../state/store'

const ICON = { size: 18, strokeWidth: 1.75 } as const
const TF_LABEL: Record<Timeframe, string> = { '1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W' }
const TV_OF: Record<Timeframe, TvInterval> = { '1h': '60', '4h': '240', '1d': 'D', '1w': 'W' }

/** Every alerting divergence (published by the runner, plus any the open chart just saw confirm), merged and newest first. */
function useAllAlerts(): { alerts: AlertItem[]; isPending: boolean; error: unknown } {
  const { data, isPending, error } = useAlerts()
  const live = useTerminal((s) => s.liveAlerts)
  const alerts = useMemo(() => {
    const byId = new Map<string, AlertItem>()
    for (const a of [...live, ...(data ?? [])]) byId.set(a.id, { ...byId.get(a.id), ...a })
    return [...byId.values()].sort((x, y) => (y.confirmed_at ?? 0) - (x.confirmed_at ?? 0))
  }, [data, live])
  return { alerts, isPending: isPending && !live.length, error }
}

export function AlertsPanel({ hidden }: { hidden: boolean }) {
  const { alerts, isPending, error } = useAllAlerts()
  const model = useDivergenceModel().data
  const label = useLabelDivergence()
  const seen = useTerminal((s) => s.seenAlerts)
  const markSeen = useTerminal((s) => s.markAlertsSeen)
  const notify = useTerminal((s) => s.notify)
  const t = useTerminal.getState()

  // Opening the screen counts every alert on it as seen (clears the navigation badge), after this render's highlights.
  useEffect(() => {
    if (!hidden && alerts.length) {
      const timer = setTimeout(() => markSeen(alerts.map((a) => a.id)), 4000)
      return () => clearTimeout(timer)
    }
  }, [hidden, alerts, markSeen])

  const open = (a: AlertItem) => {
    t.setAsset(a.asset)
    t.setChartMode('ORBIT')
    t.setTvInterval(TV_OF[a.timeframe])
    t.setView('GP')
  }
  const teach = (a: AlertItem, verdict: 'real' | 'not') =>
    label.mutate(
      { asset: a.asset, timeframe: a.timeframe, t1: a.t1, t2: a.t2, direction: a.direction, verdict },
      { onSuccess: () => notify(`LABELLED ${verdict === 'real' ? '✓ REAL' : '✗ NOT REAL'}`), onError: (e) => notify(`NOT SAVED: ${String(e)}`, true) },
    )

  return (
    <Panel
      code="ALRT"
      title="Divergence alerts"
      description="Confirmed RSI divergences on 1H, 4H, 1D and 1W that scored in the top of their timeframe. 4H and 1D ones also become suggestions; the rest are alerts only. Teach the model with ✓/✗."
      hidden={hidden}
    >
      <StatGrid>
        <StatCard icon={<BellRing {...ICON} />} label="Alerts" value={alerts.length} caption="in the last 14 days" />
        <StatCard
          icon={model?.trusted ? <ShieldCheck {...ICON} /> : <ShieldAlert {...ICON} />}
          label="Model"
          value={model ? (model.trusted ? 'trusted' : 'unproven') : '—'}
          tone={model?.trusted ? 'up' : 'warn'}
          caption={model?.trusted ? 'beats the plain rate out-of-sample' : 'scores are not yet better than the plain rate'}
        />
        <StatCard
          icon={<Check {...ICON} />}
          label="You and the market"
          value={model?.agreement?.compared ? `${model.agreement.agree}/${model.agreement.compared}` : '—'}
          caption={model ? `agree, of ${model.agreement?.labelled ?? 0} you've labelled` : 'no labels yet'}
        />
      </StatGrid>
      {!alerts.length ? (
        isPending || error ? (
          <QueryState isPending={isPending} error={error} what="alerts" />
        ) : (
          <Empty title="NO ALERTS">
            <span>No divergence has scored above its timeframe's threshold recently. The runner checks every hour; the ORBIT chart checks live.</span>
          </Empty>
        )
      ) : (
        <div className="alerts-list">
          {alerts.map((a) => {
            const up = a.direction === 'LONG'
            return (
              <div key={a.id} className={`alert-row ${seen.includes(a.id) ? '' : 'unseen'}`}>
                <button type="button" className="alert-main" onClick={() => open(a)} title="Open on the ORBIT chart">
                  <span className="alert-asset">
                    <b>{ASSET_META[a.asset].label}</b>
                    <span className="alert-tf">{TF_LABEL[a.timeframe]}</span>
                  </span>
                  <span className={`dv-dir ${up ? 'up' : 'down'}`}>
                    {up ? <ArrowUpRight size={15} strokeWidth={2} aria-hidden="true" /> : <ArrowDownRight size={15} strokeWidth={2} aria-hidden="true" />}
                    {up ? 'Bullish' : 'Bearish'} <span className="dv-kind">{a.kind}</span>
                  </span>
                  <span className="alert-facts">
                    {price(a.asset, a.p1)} → {price(a.asset, a.p2)} · RSI {a.r1.toFixed(1)} → {a.r2.toFixed(1)}
                  </span>
                  <span className="alert-score">
                    <span className="dv-score">{a.score === null ? '—' : pct(a.score)}</span>
                    {!a.trusted && <Pill tone="watch">UNPROVEN</Pill>}
                    <span className="alert-ago">{a.confirmed_at ? `${ago(a.confirmed_at * 1000)} ago` : ''}</span>
                  </span>
                </button>
                <span className="dv-teach">
                  <button type="button" className={`act take ${a.you === 'real' ? 'on' : ''}`} onClick={() => teach(a, 'real')} disabled={label.isPending}>
                    <Check size={14} strokeWidth={2} /> Real
                  </button>
                  <button type="button" className={`act skip ${a.you === 'not' ? 'on' : ''}`} onClick={() => teach(a, 'not')} disabled={label.isPending}>
                    <X size={14} strokeWidth={2} /> Not real
                  </button>
                </span>
              </div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}
