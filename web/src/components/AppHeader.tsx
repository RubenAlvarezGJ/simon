import { useEventStreamContext } from '../context/EventStreamContext';
import { formatClock, formatDate, formatUptime } from '../lib/format';

export type Tab = 'command' | 'zones' | 'rules';

const TABS: { id: Tab; label: string }[] = [
  { id: 'command', label: 'Command' },
  { id: 'zones', label: 'Zones' },
  { id: 'rules', label: 'Rules' },
];

interface Props {
  tab: Tab;
  onTab: (t: Tab) => void;
  now: Date;
  uptimeS: number;
}

export function AppHeader({ tab, onTab, now, uptimeS }: Props) {
  const { connected, hello } = useEventStreamContext();
  const zoneCount = hello ? Object.keys(hello.zones).length : 0;

  return (
    <header className="cc-header">
      <div className="cc-header-left">
        <div className="cc-brand">
          <span className="cc-brand-name">Surveillance Hub</span>
        </div>
        <nav className="cc-nav">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`cc-nav-btn${tab === t.id ? ' active' : ''}`}
              onClick={() => onTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="cc-chips">
        <div className="cc-chip">
          <span className="cc-dot" style={{ background: 'var(--ok)' }} />
          <span className="cc-chip-strong" style={{ color: 'var(--ok)' }}>ARMED</span>
        </div>
        <div className="cc-chip">
          <span
            className="cc-dot"
            style={{ background: connected ? 'var(--ac)' : 'var(--bad)' }}
          />
          <span
            className="cc-chip-strong"
            style={{ color: connected ? 'var(--ac)' : 'var(--bad)' }}
          >
            {connected ? 'WS LINK' : 'WS DOWN'}
          </span>
        </div>
        <div className="cc-chip">{zoneCount} {zoneCount === 1 ? 'ZONE' : 'ZONES'}</div>
        <div className="cc-chip">1 CAM</div>
      </div>

      <div className="cc-header-right">
        <div className="cc-meta-block">
          <span className="cc-clock">{formatClock(now)}</span>
          <span className="cc-meta-sub">{formatDate(now)} · UP {formatUptime(uptimeS)}</span>
        </div>
        <div className="cc-divider" />
        <div className="cc-meta-block">
          <span className="cc-meta-name">R. ALVAREZ</span>
          <span className="cc-meta-sub">OPERATOR</span>
        </div>
      </div>
    </header>
  );
}
