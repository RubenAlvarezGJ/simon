import { useState } from 'react';
import { AppHeader, type Tab } from './components/AppHeader';
import { CommandCenter } from './components/CommandCenter';
import { ZoneEditor } from './components/ZoneEditor';
import { RuleEditor } from './components/RuleEditor';
import { EventStreamProvider } from './context/EventStreamContext';
import { useDerivedTelemetry } from './hooks/useDerivedTelemetry';
import './App.css';

function Dashboard() {
  const [tab, setTab] = useState<Tab>('home');
  const { now, fps, spark, uptimeS } = useDerivedTelemetry();

  return (
    <div className="cc-app">
      <AppHeader tab={tab} onTab={setTab} now={now} uptimeS={uptimeS} />

      {tab === 'home' && <CommandCenter now={now} fps={fps} spark={spark} />}
      {tab === 'zones' && <ZoneEditor />}
      {tab === 'rules' && <RuleEditor />}
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
