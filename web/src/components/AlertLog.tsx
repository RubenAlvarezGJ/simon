import { useEventStreamContext } from '../context/EventStreamContext';
import { timeAgo } from '../lib/format';
import type { Severity } from '../lib/types';

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--bad)',
  high: 'var(--warn)',
  low: 'var(--ac)',
};

export function AlertLog() {
  const { recent_alerts } = useEventStreamContext();

  return (
    <div className="cc-rail-panel alerts">
      <div className="cc-panel-head">
        <span className="cc-panel-title">ALERT FEED</span>
        <span className="cc-panel-meta">{recent_alerts.length} ACTIVE</span>
      </div>

      {recent_alerts.length === 0 ? (
        <div className="cc-empty">No alerts yet.</div>
      ) : (
        <div className="cc-alert-list">
          {recent_alerts.map((a, i) => {
            const sev: Severity = a.severity ?? 'high';
            const color = SEV_COLOR[sev];
            return (
              <div
                key={`${a.rule_name}-${a.triggered_at}-${i}`}
                className="cc-alert"
                style={{ borderLeftColor: color }}
              >
                <div className="cc-alert-head">
                  <span className="cc-alert-rule">{a.rule_name}</span>
                  <span className="cc-alert-sev" style={{ color, borderColor: color }}>
                    {sev.toUpperCase()}
                  </span>
                </div>
                <div className="cc-alert-meta">
                  <span>TRK [{a.tracker_ids.join(', ')}]</span>
                  <span>{timeAgo(a.triggered_at)}</span>
                </div>
                {a.rule_description && <div className="cc-alert-desc">{a.rule_description}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
