import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '.'
import type { Asset, DecisionRequest } from './types'

const MIN = 60_000

export const useSystem = () => useQuery({ queryKey: ['system'], queryFn: api.system, refetchInterval: 15_000 })
export const useQuotes = () => useQuery({ queryKey: ['quotes'], queryFn: api.quotes, refetchInterval: MIN })
export const useCandles = (a: Asset) => useQuery({ queryKey: ['candles', a], queryFn: () => api.candles(a), refetchInterval: 10 * MIN })
export const useSignals = (a: Asset) => useQuery({ queryKey: ['signals', a], queryFn: () => api.signals(a), refetchInterval: 10 * MIN })
export const useRegime = () => useQuery({ queryKey: ['regime'], queryFn: api.regime, refetchInterval: 10 * MIN })
export const useSky = () => useQuery({ queryKey: ['sky'], queryFn: api.sky, refetchInterval: 30 * MIN })
export const useTransits = (from?: string, to?: string) =>
  useQuery({ queryKey: ['transits', from ?? '', to ?? ''], queryFn: () => api.transits(from, to), refetchInterval: 30 * MIN })
export const usePlaybookOverview = () => useQuery({ queryKey: ['playbook'], queryFn: api.playbookOverview, refetchInterval: 30 * MIN })
export const usePlaybook = (a: Asset) => useQuery({ queryKey: ['playbook', a], queryFn: () => api.playbook(a), refetchInterval: 30 * MIN })
export const usePattern = (a: Asset, id: string | null) =>
  useQuery({ queryKey: ['pattern', a, id], queryFn: () => api.pattern(a, id!), enabled: !!id })

/** Which backend layers exist yet. Screens for unbuilt layers read this instead of guessing. */
export function useComponents() {
  const { data, isError, error, isPending } = useSystem()
  return { components: data?.components, isError, error, isPending }
}

export const useSuggestions = (enabled: boolean) =>
  useQuery({ queryKey: ['suggestions'], queryFn: api.suggestions, refetchInterval: 30_000, enabled })
export const useJournal = (enabled: boolean) => useQuery({ queryKey: ['journal'], queryFn: api.journal, enabled })
export const useDrift = (enabled: boolean) => useQuery({ queryKey: ['drift'], queryFn: api.drift, enabled })
export const useBacktest = (enabled: boolean) => useQuery({ queryKey: ['backtest'], queryFn: api.backtest, enabled, refetchInterval: 30 * MIN })
export const useCalibration = (enabled: boolean) => useQuery({ queryKey: ['calibration'], queryFn: api.calibration, enabled, refetchInterval: 30 * MIN })
export const useModel = (a: Asset) => useQuery({ queryKey: ['model', a], queryFn: () => api.model(a), refetchInterval: 30 * MIN, retry: false })

export function useDecide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, req }: { id: string; req: DecisionRequest }) => api.decide(id, req),
    onSettled: () => {
      for (const key of ['suggestions', 'journal', 'system']) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

/** The active analysis run; polled quickly while one is going. */
export function useCurrentRun() {
  return useQuery({
    queryKey: ['run', 'current'],
    queryFn: api.currentRun,
    refetchInterval: (q) => (q.state.data ? 2000 : 15_000),
  })
}
export const useRuns = () => useQuery({ queryKey: ['runs'], queryFn: api.runs, refetchInterval: 30_000 })
export const useSchedule = () => useQuery({ queryKey: ['schedule'], queryFn: api.schedule, refetchInterval: 60_000 })
export const useIntraday = (a: Asset, at: string | null, beforeHours: number, afterHours: number) =>
  useQuery({ queryKey: ['intraday', a, at, beforeHours, afterHours], queryFn: () => api.intraday(a, at!, beforeHours, afterHours), enabled: !!at })

export function useStartRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (opts: { placebo: boolean; refresh: boolean }) => api.startRun(opts),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['run'] })
      qc.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}
