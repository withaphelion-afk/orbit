import { CommandBar } from './components/CommandBar'
import { FunctionBar } from './components/FunctionBar'
import { Palette } from './components/Palette'
import { useLiveFeed } from './hooks/useLiveFeed'
import { useTerminalKeys } from './hooks/useTerminalKeys'
import { AstroPanel } from './panels/AstroPanel'
import { ChartPanel } from './panels/ChartPanel'
import { DriftPanel } from './panels/DriftPanel'
import { HelpPanel } from './panels/HelpPanel'
import { JournalPanel } from './panels/JournalPanel'
import { SuggestionsPanel } from './panels/SuggestionsPanel'
import { SystemPanel } from './panels/SystemPanel'
import { WatchlistPanel } from './panels/WatchlistPanel'
import { useTerminal } from './state/store'

/**
 * The terminal. Every panel stays mounted and is hidden rather than
 * unmounted, so switching functions never reloads the live chart or loses a
 * half-typed decision note.
 */
export function App() {
  useLiveFeed()
  useTerminalKeys()
  const view = useTerminal((s) => s.view)

  return (
    <div className="term">
      <CommandBar />
      <main className={`main ${view === 'MON' ? 'mon' : 'max'}`}>
        <ChartPanel hidden={view !== 'MON' && view !== 'GP'} />
        <WatchlistPanel hidden={view !== 'MON'} />
        <SuggestionsPanel hidden={view !== 'SUGG'} />
        <JournalPanel hidden={view !== 'JRNL'} />
        <DriftPanel hidden={view !== 'DRIFT'} />
        <AstroPanel hidden={view !== 'ASTRO'} />
        <SystemPanel hidden={view !== 'SYS'} />
        <HelpPanel hidden={view !== 'HELP'} />
      </main>
      <FunctionBar />
      <Palette />
    </div>
  )
}
