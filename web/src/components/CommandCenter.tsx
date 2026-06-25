import { LiveFeed } from './LiveFeed';
import { TelemetryStrip } from './TelemetryStrip';
import { ThreatPanel } from './ThreatPanel';
import { AlertLog } from './AlertLog';
import type { SparkBar } from '../hooks/useDerivedTelemetry';

interface Props {
  now: Date;
  fps: number;
  spark: SparkBar[];
}

export function CommandCenter({ now, fps, spark }: Props) {
  return (
    <main className="cc-main">
      <div className="cc-left">
        <LiveFeed fps={fps} now={now} />
        <TelemetryStrip fps={fps} spark={spark} />
      </div>
      <div className="cc-rail">
        <ThreatPanel />
        <AlertLog />
      </div>
    </main>
  );
}
