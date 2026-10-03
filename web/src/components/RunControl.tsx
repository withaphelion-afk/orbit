import { useQueryClient } from '@tanstack/react-query'
import { CalendarClock, LoaderCircle, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useCurrentRun, useRuns, useSchedule, useStartRun } from '../api/hooks'
import type { AnalysisRun } from '../api/types'
import { useNow } from '../hooks/useLiveFeed'
import { ago, day, hhmm, num } from '../lib/format'
import { useTerminal } from '../state/store'

const WEEKDAYS = ['Mondays', 'Tuesdays', 'Wednesdays', 'Thursdays', 'Fridays', 'Saturdays', 'Sundays']

function duration(run: AnalysisRun, now: number): string {
  const end = run.finished_at ? Date.parse(run.finished_at) : now
  const s = Math.max(0, Math.round((end - Date.parse(run.started_at ?? run.created_at)) / 1000))
  return s < 90 ? `${s}s` : `${Math.round(s / 60)} min`
}

/** Start an analysis run, watch it, and see the schedule. Used on ASTRO → PLAYBOOK and SYS. */
export function RunControl({ compact = false }: { compact?: boolean }) {
  const current = useCurrentRun()
  const runs = useRuns()
  const schedule = useSchedule()
  const start = useStartRun()
  const notify = useTerminal((s) => s.notify)
  const qc = useQueryClient()
  const [placebo, setPlacebo] = useState(false)
  const [refresh, setRefresh] = useState(true)
  const now = useNow(1000)

  // When a run finishes, reload everything its results feed.
  const running = current.data ?? null
  const prev = useRef<string | null>(null)
  useEffect(() => {
    if (prev.current && !running) {
      for (const key of ['playbook', 'pattern', 'transits', 'system', 'runs', 'sky']) qc.invalidateQueries({ queryKey: [key] })
      notify('ANALYSIS RUN FINISHED · RESULTS RELOADED')
    }
    prev.current = running?.id ?? null
  }, [running, qc, notify])

  const last = runs.data?.find((r) => r.status === 'succeeded' || r.status === 'failed')
  const sched = schedule.data
  const busy = !!running || start.isPending

  const onStart = () =>
    start.mutate(
      { placebo, refresh },
      {
        onSuccess: () => notify(`ANALYSIS STARTED${placebo ? ' · WITH PLACEBO CHECK' : ''}`),
        onError: (e) => notify(String(e instanceof Error ? e.message : e).toUpperCase(), true),
      },
    )

  return (
    <div className={`runctl ${compact ? 'compact' : ''}`}>
      <div className="runctl-row">
        <button className="act run" onClick={onStart} disabled={busy} title="Re-run every check on the latest data">
          {busy ? <LoaderCircle className="runctl-spin" size={15} strokeWidth={2} aria-hidden /> : <Play size={14} strokeWidth={2} aria-hidden />}
          {running ? 'RUNNING…' : start.isPending ? 'STARTING…' : 'RUN ANALYSIS'}
        </button>
        <label className="chk" title="Fetch the latest prices and ephemeris before testing">
          <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} disabled={!!running} /> Refresh data first
        </label>
        <label className="chk" title="Also re-run everything on 32 fake calendars to check the method isn't fooled by noise">
          <input type="checkbox" checked={placebo} onChange={(e) => setPlacebo(e.target.checked)} disabled={!!running} /> Include placebo check (~40 min)
        </label>
      </div>
      <div className="runctl-info">
        {running ? (
          <div className="runctl-progress">
            <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(running.progress * 100)}>
              <i style={{ width: `${Math.round(running.progress * 100)}%` }} />
            </div>
            <span>
              {Math.round(running.progress * 100)}% · {running.step} · {duration(running, now)} · {running.trigger === 'schedule' ? 'scheduled run' : 'started here'}
            </span>
          </div>
        ) : last ? (
          <div className={`runctl-last ${last.status === 'failed' ? 'down' : ''}`}>
            Last run {day(last.created_at)} {hhmm(last.created_at)} · {last.trigger === 'schedule' ? 'scheduled' : 'manual'} · {duration(last, now)} ·{' '}
            {last.status === 'failed'
              ? `failed: ${last.error ?? 'unknown error'}`
              : `${num(last.summary.total_tests ?? 0, 0)} tests · ${last.changes.length} label change${last.changes.length === 1 ? '' : 's'}${
                  last.summary.placebo ? ` · placebo ${last.summary.placebo.runs_with_any_discovery}/${last.summary.placebo.placebo_runs}` : ''
                }`}
          </div>
        ) : (
          <div className="runctl-last dim">No run from here yet.</div>
        )}
        {sched && (
          <div className="runctl-sched dim">
            <CalendarClock size={13} strokeWidth={1.75} aria-hidden />
            <span>
              {sched.enabled
                ? `Scheduled daily at ${sched.daily_at_utc} UTC by the runner · ${WEEKDAYS[sched.placebo_weekday]} include the placebo check · `
                : 'Scheduled runs are off in settings · '}
              {sched.runner_running
                ? sched.next_at
                  ? `next ${day(sched.next_at)} ${hhmm(sched.next_at)} (in ${ago(now - (Date.parse(sched.next_at) - now), now)})`
                  : 'runner up'
                : 'runner not running, so nothing is scheduled'}
            </span>
          </div>
        )}
      </div>
      {!compact && last && last.changes.length > 0 && (
        <details className="runctl-changes">
          <summary>What changed in the last run ({last.changes.length})</summary>
          <ul>
            {last.changes.slice(0, 30).map((c) => (
              <li key={`${c.asset}-${c.pattern_id}-${c.kind}`}>
                {c.asset} · {c.description} ({c.kind}): {c.before ?? '—'} → {c.after}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
