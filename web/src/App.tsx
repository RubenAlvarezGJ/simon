import { useState } from 'react';
import { AppHeader, type Tab } from './components/AppHeader';
import { CommandCenter } from './components/CommandCenter';
import { ZoneEditor } from './components/ZoneEditor';
import { RuleEditor } from './components/RuleEditor';
import { EventStreamProvider } from './context/EventStreamContext';
import { useDerivedTelemetry } from './hooks/useDerivedTelemetry';
import './App.css';

function Dashboard() {
  const [tab, setTab] = useState<Tab>('command');
  const { now, fps, spark, uptimeS } = useDerivedTelemetry();

  return (
    <div className="cc-app">
      <AppHeader tab={tab} onTab={setTab} now={now} uptimeS={uptimeS} />

      {tab === 'command' && <CommandCenter now={now} fps={fps} spark={spark} />}
      {tab === 'zones' && <ZoneEditor />}
      {tab === 'rules' && (
        <div className="cc-editor-page">
          <RuleEditor />
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <EventStreamProvider>
      <Dashboard />
    </EventStreamProvider>
  );
}
