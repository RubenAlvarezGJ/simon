import { useState } from 'react';
import { LiveFeed } from './components/LiveFeed';
import { ThreatPanel } from './components/ThreatPanel';
import { AlertLog } from './components/AlertLog';
import { StatsPanel } from './components/StatsPanel';
import { ZoneEditor } from './components/ZoneEditor';
import { RuleEditor } from './components/RuleEditor';
import { EventStreamProvider } from './context/EventStreamContext';
import './App.css';

type Tab = 'overview' | 'zones' | 'rules';

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');

  return (
    <EventStreamProvider>
      <div className="app-shell">
        <header className="app-header">
          <h1>Threat Detector — Command Center</h1>
          <nav>
            <button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>Overview</button>
            <button className={tab === 'zones' ? 'active' : ''} onClick={() => setTab('zones')}>Zones</button>
            <button className={tab === 'rules' ? 'active' : ''} onClick={() => setTab('rules')}>Rules</button>
          </nav>
        </header>

        {tab === 'overview' && (
          <div className="overview-grid">
            <div className="feed-cell"><LiveFeed /></div>
            <div className="right-col">
              <ThreatPanel />
              <AlertLog />
            </div>
            <div className="bottom-row">
              <StatsPanel />
            </div>
          </div>
        )}
        {tab === 'zones' && <ZoneEditor />}
        {tab === 'rules' && <RuleEditor />}
      </div>
    </EventStreamProvider>
  );
}
