import { useEventStreamContext } from '../context/EventStreamContext';
import { formatAge } from '../lib/format';

function confColor(conf: number): string {
  if (conf >= 0.9) return 'var(--bad)';
  if (conf >= 0.8) return 'var(--warn)';
  return 'var(--ac)';
}

export function ThreatPanel() {
  const { threats } = useEventStreamContext();

  return (
    <div className="cc-rail-panel tracked">
      <div className="cc-panel-head">
        <span className="cc-panel-title">TRACKED OBJECTS</span>
        <span className="cc-panel-meta">
          <span className="cc-dot" style={{ background: 'var(--ac)' }} />
          LIVE · {threats.length}
        </span>
      </div>

      <div className="cc-trk-grid cc-trk-head">
        <span />
        <span>ID</span>
        <span>CLASS · ZONE</span>
        <span className="r">CONF</span>
        <span className="r">AGE</span>
      </div>

      {threats.length === 0 ? (
        <div className="cc-empty">No tracked objects.</div>
      ) : (
        threats.map((t) => {
          const zone = t.active_zones.length > 0 ? t.active_zones.join(' · ') : '—';
          return (
            <div
              key={t.tracker_id}
              className="cc-trk-grid cc-trk-row"
              style={{ background: t.alert_fired ? 'rgba(255,77,77,.05)' : 'transparent' }}
            >
              <span className="cc-trk-dot" style={{ background: t.alert_fired ? 'var(--bad)' : 'var(--ac)' }} />
              <span className="cc-trk-id">#{t.tracker_id}</span>
              <span style={{ minWidth: 0 }}>
                <span className="cc-trk-cls">{t.class_name}</span>
                <span className="cc-trk-zone">{zone}</span>
              </span>
              <span className="cc-trk-conf" style={{ color: confColor(t.confidence) }}>
                {t.confidence.toFixed(2)}
              </span>
              <span className="cc-trk-age">{formatAge(t.age_seconds)}</span>
            </div>
          );
        })
      )}
    </div>
  );
}
