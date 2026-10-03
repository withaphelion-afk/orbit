import type { ReactNode } from 'react'

interface Props {
  code: string
  /** Leave out (with no description or tools) for a bare panel: just the body, e.g. a full-bleed chart. */
  title?: string
  /** One plain sentence under the title saying what this screen is for. */
  description?: ReactNode
  /** Controls for this panel (tabs, filters, chart options), shown as a toolbar under the title. */
  tools?: ReactNode
  hidden?: boolean
  className?: string
  children: ReactNode
}

/** A terminal panel: a card with its title (and description), an optional toolbar, and a scrolling body. */
export function Panel({ code, title, description, tools, hidden, className = '', children }: Props) {
  return (
    <section className={`panel p-${code} ${className}`} hidden={hidden}>
      {title && (
        <header className={`ph ${description ? 'has-desc' : ''}`}>
          <h2 className="ptitle">{title}</h2>
          {description && <p className="pdesc">{description}</p>}
        </header>
      )}
      {tools && <div className="ptools">{tools}</div>}
      <div className="pb">{children}</div>
    </section>
  )
}
