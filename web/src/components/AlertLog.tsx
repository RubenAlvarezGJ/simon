import { useEventStreamContext } from '../context/EventStreamContext';

function anyCritical(snapshots: { is_critical: boolean }[]): boolean {
  return snapshots.some((s) => s.is_critical);
}

function timeAgo(triggered_at: number): string {
  const sec = Math.max(0, Math.floor((Date.now() / 1000) - triggered_at));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  return `${hr}h ago`;
}

export function AlertLog() {
  const { recent_alerts } = useEventStreamContext();

  return (
    <div className="panel">
      <h3>Alerts ({recent_alerts.length})</h3>
      {recent_alerts.length === 0 ? (
        <div className="muted">No alerts yet.</div>
      ) : (
        <ul className="alert-list">
          {recent_alerts.map((a, i) => {
            const cls = anyCritical(a.threat_snapshots) ? 'critical' : 'non-critical';
            return (
              <li key={`${a.rule_name}-${a.triggered_at}-${i}`} className={`alert ${cls}`}>
                <div className="alert-head">
                  <strong>{a.rule_name}</strong>
                  <span className="muted">{timeAgo(a.triggered_at)}</span>
                </div>
                <div className="alert-body">
                  ids: [{a.tracker_ids.join(', ')}]
                </div>
                {a.rule_description && (
                  <div className="alert-desc">{a.rule_description}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
