/** Reads the design tokens from CSS so canvas charts use the same colours as the DOM. */
export function readTheme() {
  const s = getComputedStyle(document.documentElement)
  const v = (n: string) => s.getPropertyValue(n).trim()
  return {
    panel: v('--panel'),
    line: v('--line'),
    line2: v('--line-2'),
    accent: v('--accent'),
    accentLo: v('--accent-lo'),
    text: v('--text'),
    text2: v('--text-2'),
    text3: v('--text-3'),
    up: v('--up'),
    down: v('--down'),
    warn: v('--warn'),
    astro: v('--astro'),
    mono: v('--mono'),
  }
}
export type Theme = ReturnType<typeof readTheme>
