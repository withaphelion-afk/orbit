import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { source } from '.'
import type { Asset, DecisionRequest } from './types'

export const useQuotes = () => useQuery({ queryKey: ['quotes'], queryFn: () => source.quotes(), refetchInterval: 60_000 })
export const useCandles = (a: Asset) => useQuery({ queryKey: ['candles', a], queryFn: () => source.candles(a) })
export const useSignals = (a: Asset) => useQuery({ queryKey: ['signals', a], queryFn: () => source.signals(a) })
export const useSuggestions = () => useQuery({ queryKey: ['suggestions'], queryFn: () => source.suggestions(), refetchInterval: 30_000 })
export const useJournal = () => useQuery({ queryKey: ['journal'], queryFn: () => source.journal() })
export const useDrift = () => useQuery({ queryKey: ['drift'], queryFn: () => source.drift() })
export const useAstro = () => useQuery({ queryKey: ['astro'], queryFn: () => source.astro() })
export const useSystem = () => useQuery({ queryKey: ['system'], queryFn: () => source.system(), refetchInterval: 15_000 })

export function useDecide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, req }: { id: string; req: DecisionRequest }) => source.decide(id, req),
    onSettled: () => {
      for (const key of ['suggestions', 'journal', 'system']) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}
