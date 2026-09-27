import { useEffect, useState } from 'react'
import { source } from '../api'
import { useTerminal } from '../state/store'

/** Subscribes the store to the source's tick stream for the life of the app. */
export function useLiveFeed() {
  useEffect(() => {
    const { applyTick, setFeedConnected } = useTerminal.getState()
    return source.subscribeTicks((t) => applyTick(t.asset, t.price), setFeedConnected)
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
