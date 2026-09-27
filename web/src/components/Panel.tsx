import type { ReactNode } from 'react'
import type { View } from '../lib/commands'
import { useTerminal } from '../state/store'

interface Props {
  code: string
  title: string
  meta?: ReactNode
  hidden?: boolean
  className?: string
  children: ReactNode
}

/**
 * A terminal panel: code chip, title, right-aligned meta, scrolling body.
 * Clicking a function's code maximises it; clicking again returns to MON.
 */
export function Panel({ code, title, meta, hidden, className = '', children }: Props) {
  const view = useTerminal((s) => s.view)
  const setView = useTerminal((s) => s.setView)
  const isView = ['GP', 'SUGG', 'JRNL', 'DRIFT', 'ASTRO', 'SYS', 'HELP'].includes(code)
  return (
    <section className={`panel p-${code} ${className}`} hidden={hidden}>
      <header className="ph">
        {isView ? (
          <button className="code" onClick={() => setView(view === code ? 'MON' : (code as View))} title={view === code ? 'Back to MON' : `Maximise ${code}`}>
            {code}
          </button>
        ) : (
          <span className="code">{code}</span>
        )}
        <span className="ptitle">{title}</span>
        {meta && <div className="pmeta">{meta}</div>}
      </header>
      <div className="pb">{children}</div>
    </section>
  )
}
