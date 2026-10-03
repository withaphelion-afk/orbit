import { lazy, Suspense, useState } from 'react'
import { CommandBar } from './components/CommandBar'
import { FunctionBar } from './components/FunctionBar'
import { Palette } from './components/Palette'
import { useLiveFeed } from './hooks/useLiveFeed'
import { useTerminalKeys } from './hooks/useTerminalKeys'
import { ChartPanel } from './panels/ChartPanel'
import { WatchlistPanel } from './panels/WatchlistPanel'
import { useTerminal } from './state/store'

// Loaded the first time their function key is pressed, so the opening screen
// downloads less and doesn't fetch data for screens you haven't opened.
const SuggestionsPanel = lazy(() => import('./panels/SuggestionsPanel').then((m) => ({ default: m.SuggestionsPanel })))
const JournalPanel = lazy(() => import('./panels/JournalPanel').then((m) => ({ default: m.JournalPanel })))
const DriftPanel = lazy(() => import('./panels/DriftPanel').then((m) => ({ default: m.DriftPanel })))
const AstroPanel = lazy(() => import('./panels/AstroPanel').then((m) => ({ default: m.AstroPanel })))
const SystemPanel = lazy(() => import('./panels/SystemPanel').then((m) => ({ default: m.SystemPanel })))
const AlertsPanel = lazy(() => import('./panels/AlertsPanel').then((m) => ({ default: m.AlertsPanel })))
const HelpPanel = lazy(() => import('./panels/HelpPanel').then((m) => ({ default: m.HelpPanel })))

/**
 * The terminal. A panel is mounted the first time its function is opened and
 * then stays mounted, hidden rather than unmounted, so switching functions
 * never reloads the live chart or loses a half-typed decision note.
 */
export function App() {
  useLiveFeed()
  useTerminalKeys()
  const view = useTerminal((s) => s.view)
  const [opened, setOpened] = useState(() => new Set([view]))
  if (!opened.has(view)) setOpened(new Set(opened).add(view))

  return (
    <div className="term">
      <CommandBar />
      <main className={`main ${view === 'MON' ? 'mon' : 'max'}`}>
        <ChartPanel hidden={view !== 'MON' && view !== 'GP'} />
        <WatchlistPanel hidden={view !== 'MON'} />
        <Suspense fallback={null}>
          {opened.has('SUGG') && <SuggestionsPanel hidden={view !== 'SUGG'} />}
          {opened.has('JRNL') && <JournalPanel hidden={view !== 'JRNL'} />}
          {opened.has('DRIFT') && <DriftPanel hidden={view !== 'DRIFT'} />}
          {opened.has('ASTRO') && <AstroPanel hidden={view !== 'ASTRO'} />}
          {opened.has('SYS') && <SystemPanel hidden={view !== 'SYS'} />}
          {opened.has('HELP') && <HelpPanel hidden={view !== 'HELP'} />}
          {opened.has('ALRT') && <AlertsPanel hidden={view !== 'ALRT'} />}
        </Suspense>
      </main>
      <FunctionBar />
      <Palette />
    </div>
  )
}
