import { useEventStreamContext } from '../context/eventStream';
import type { SparkBar } from '../hooks/useDerivedTelemetry';
import { num } from '../lib/format';

interface Props {
  fps: number;
  spark: SparkBar[];
}

export function TelemetryStrip({ fps, spark }: Props) {
  const { threats, alert_tally, pipeline_stats: p, dispatcher_stats: d } = useEventStreamContext();

  const inZone = threats.filter((t) => t.active_zones.length > 0).length;
  const alerts = Object.values(alert_tally.counts).reduce((sum, n) => sum + n, 0);
  const critical = alert_tally.counts.critical;

  return (
    <div className="cc-strip">
      {/* throughput + sparkline */}
      <div className="cc-card" style={{ flex: 1.3 }}>
        <div className="cc-card-label">THROUGHPUT</div>
        <div className="cc-card-row">
          <div className="cc-card-value">
            {fps}<span className="cc-card-unit"> fps</span>
          </div>
          <div className="cc-spark">
            {spark.map((b, i) => (
              <div
                key={i}
                className="cc-spark-bar"
                style={{ height: `${b.h}px`, animationDelay: `${b.d}s` }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* inference */}
      <div className="cc-card" style={{ flex: 1 }}>
        <div className="cc-card-label">INFERENCE</div>
        <div className="cc-card-value">
          {num(p.engine_avg_inference_ms)}<span className="cc-card-unit"> ms</span>
        </div>
        <div className="cc-card-sub">YOLO11 · avg / frame</div>
      </div>

      {/* active tracks */}
      <div className="cc-card" style={{ flex: 1 }}>
        <div className="cc-card-label">ACTIVE TRACKS</div>
        <div className="cc-card-value accent">{threats.length}</div>
        <div className="cc-card-sub">{inZone} in zone</div>
      </div>

      {/* alerts */}
      <div className="cc-card" style={{ flex: 1 }}>
        <div className="cc-card-label">ALERTS</div>
        <div className="cc-card-value">{num(alerts)}</div>
        <div className={`cc-card-sub${critical > 0 ? ' bad' : ''}`}>{critical} critical</div>
      </div>

      {/* frames read */}
      <div className="cc-card" style={{ flex: 1.45 }}>
        <div className="cc-card-label">FRAMES READ</div>
        <div className="cc-card-value sm">{num(p.reader_frames_read)}</div>
        <div className="cc-card-sub">{num(p.reader_frames_dropped)} dropped</div>
      </div>

      {/* dispatcher */}
      <div className="cc-card" style={{ flex: 1 }}>
        <div className="cc-card-label">DISPATCH</div>
        <div className="cc-card-value ok">
          {num(d.delivered)}<span className="cc-card-unit">/{num(d.enqueued)}</span>
        </div>
        <div className="cc-card-sub">{num(d.sink_errors)} errors</div>
      </div>
    </div>
  );
}
