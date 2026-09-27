import { Command } from 'cmdk'
import { ASSETS, ASSET_META } from '../config'
import { FUNCTIONS } from '../lib/commands'
import { runCommand, useTerminal } from '../state/store'

const ITEMS = [
  ...FUNCTIONS.map((f) => ({ cmd: f.code, desc: f.desc, key: f.key })),
  ...ASSETS.map((a, i) => ({ cmd: `${ASSET_META[a].label} GP`, desc: `Chart ${ASSET_META[a].name}`, key: String(i + 1) })),
]

export function Palette() {
  const open = useTerminal((s) => s.paletteOpen)
  const setOpen = useTerminal((s) => s.setPaletteOpen)
  const setChartMode = useTerminal((s) => s.setChartMode)

  const pick = (fn: () => void) => {
    setOpen(false)
    fn()
  }

  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Command palette" overlayClassName="pal-overlay" contentClassName="pal">
      <Command.Input placeholder="Search commands" />
      <Command.List>
        <Command.Empty>No command matches.</Command.Empty>
        {ITEMS.map((it) => (
          <Command.Item key={it.cmd} value={`${it.cmd} ${it.desc}`} onSelect={() => pick(() => runCommand(it.cmd))}>
            <b>{it.cmd}</b>
            <span>{it.desc}</span>
            <kbd>{it.key}</kbd>
          </Command.Item>
        ))}
        <Command.Item value="chart live tradingview" onSelect={() => pick(() => setChartMode('LIVE'))}>
          <b>CHART LIVE</b>
          <span>TradingView live chart</span>
          <kbd />
        </Command.Item>
        <Command.Item value="chart orbit overlays signals" onSelect={() => pick(() => setChartMode('ORBIT'))}>
          <b>CHART ORBIT</b>
          <span>Orbit chart with signals, levels and transits</span>
          <kbd />
        </Command.Item>
      </Command.List>
    </Command.Dialog>
  )
}
