import { useEventStreamContext } from '../context/EventStreamContext';

export function ThreatPanel() {
  const { threats } = useEventStreamContext();

  if (threats.length === 0) {
    return (
      <div className="panel">
        <h3>Confirmed threats</h3>
        <div className="muted">No confirmed threats.</div>
      </div>
    );
  }

  return (
    <div className="panel">
      <h3>Confirmed threats ({threats.length})</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Class</th>
            <th>Conf</th>
            <th>Zones</th>
            <th>Age (s)</th>
          </tr>
        </thead>
        <tbody>
          {threats.map((t) => (
            <tr key={t.tracker_id}>
              <td>{t.tracker_id}</td>
              <td>{t.class_name}</td>
              <td>{t.confidence.toFixed(2)}</td>
              <td>{t.active_zones.join(', ') || '-'}</td>
              <td>{t.age_seconds.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
