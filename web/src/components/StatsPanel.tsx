import { useEventStreamContext } from '../context/EventStreamContext';

function num(v: unknown): string {
  if (typeof v === 'number') return v.toFixed(v % 1 === 0 ? 0 : 2);
  return String(v ?? '-');
}

export function StatsPanel() {
  const { pipeline_stats: p, dispatcher_stats: d } = useEventStreamContext();

  return (
    <div className="panel stats-panel">
      <h3>Pipeline + dispatcher</h3>
      <div className="stats-grid">
        <div>
          <h4>Pipeline</h4>
          <dl>
            <dt>frames read</dt><dd>{num(p.reader_frames_read)}</dd>
            <dt>frames dropped</dt><dd>{num(p.reader_frames_dropped)}</dd>
            <dt>processed</dt><dd>{num(p.engine_frames_processed)}</dd>
            <dt>skipped</dt><dd>{num(p.engine_frames_skipped)}</dd>
            <dt>avg ms</dt><dd>{num(p.engine_avg_inference_ms)}</dd>
          </dl>
        </div>
        <div>
          <h4>Dispatcher</h4>
          <dl>
            <dt>enqueued</dt><dd>{num(d.enqueued)}</dd>
            <dt>delivered</dt><dd>{num(d.delivered)}</dd>
            <dt>dropped</dt><dd>{num(d.dropped)}</dd>
            <dt>sink errors</dt><dd>{num(d.sink_errors)}</dd>
          </dl>
        </div>
      </div>
    </div>
  );
}
