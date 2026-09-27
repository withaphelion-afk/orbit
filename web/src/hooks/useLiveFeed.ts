import { useEffect, useState } from 'react'
import { api } from '../api'
import { useTerminal } from '../state/store'

/** Subscribes the store to the API's live price stream for the life of the app. */
export function useLiveFeed() {
  useEffect(() => {
    const { applyTick, setFeedConnected } = useTerminal.getState()
    return api.subscribeTicks((t) => applyTick(t.asset, t.price, t.source), setFeedConnected)
  }, [])
}

/** Re-renders every `ms` so clocks and ages stay current. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(id)
  }, [ms])
  return now
}
