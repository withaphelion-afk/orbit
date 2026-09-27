import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Text that flashes green or red whenever `value` moves. */
export function Flash({ value, className = '', children }: { value: number; className?: string; children: ReactNode }) {
  const prev = useRef(value)
  const [flash, setFlash] = useState<{ dir: 1 | -1; n: number } | null>(null)
  useEffect(() => {
    if (value === prev.current) return
    const dir = value > prev.current ? 1 : -1
    prev.current = value
    setFlash((f) => ({ dir, n: (f?.n ?? 0) + 1 }))
  }, [value])
  return (
    <span key={flash?.n ?? 0} className={`${className} ${flash ? (flash.dir > 0 ? 'flash-up' : 'flash-down') : ''}`}>
      {children}
    </span>
  )
}

/** Area sparkline that stretches to its container's width. */
export function Sparkline({ values, height = 34 }: { values: number[]; height?: number }) {
  if (values.length < 2) return null
  const W = 300
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pts = values.map((v, i) => [(i / (values.length - 1)) * W, height - 2 - ((v - lo) / (hi - lo || 1)) * (height - 4)])
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('')
  const color = values[values.length - 1] >= values[0] ? 'var(--up)' : 'var(--down)'
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" aria-hidden="true" style={{ height }}>
      <path d={`${d} L${W} ${height} L0 ${height}Z`} fill={color} opacity={0.1} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.3} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function Pill({ tone, children, title }: { tone: 'off' | 'mock' | 'ok' | 'watch' | 'drift' | 'astro'; children: ReactNode; title?: string }) {
  return (
    <em className={`pill ${tone}`} title={title}>
      {children}
    </em>
  )
}

export function Seg<T extends string>({ options, value, onChange, label }: { options: { label: string; value: T }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? 'on' : ''} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <b>{title}</b>
      {children}
    </div>
  )
}
