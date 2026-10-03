import { useEffect, useRef } from 'react'
import { readTheme } from '../../lib/theme'

const EMBED_SRC = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'

interface Props {
  symbol: string // e.g. "BINANCE:BTCUSDT"
  interval: string // TradingView interval code: "60", "240", "D", "W"
}

function embed(el: HTMLElement, symbol: string, interval: string) {
  const th = readTheme()
  el.innerHTML = ''
  const widget = document.createElement('div')
  widget.className = 'tradingview-widget-container__widget'
  el.appendChild(widget)
  const script = document.createElement('script')
  script.src = EMBED_SRC
  script.type = 'text/javascript'
  script.async = true
  script.innerHTML = JSON.stringify({
    autosize: true,
    symbol,
    interval,
    timezone: 'Etc/UTC',
    theme: 'dark',
    style: '1',
    locale: 'en',
    backgroundColor: th.panel,
    gridColor: th.line,
    allow_symbol_change: false,
    withdateranges: true,
    hide_side_toolbar: false,
    save_image: false,
    calendar: false,
    support_host: 'https://www.tradingview.com',
  })
  el.appendChild(script)
}

/**
 * TradingView's Advanced Chart widget: live market data streamed by
 * TradingView itself. It is an iframe, so Orbit can't draw its own overlays on
 * it; the ORBIT chart mode covers that. Re-embeds when symbol or interval change.
 */
export function TradingViewChart({ symbol, interval }: Props) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    // Embed on the next task: the embed script looks up its own parent node
    // when it runs, so it must not be removed first (StrictMode mounts twice).
    const timer = setTimeout(() => embed(el, symbol, interval), 0)
    return () => {
      clearTimeout(timer)
      el.innerHTML = ''
    }
  }, [symbol, interval])

  return <div className="tradingview-widget-container tv-host" ref={host} />
}
