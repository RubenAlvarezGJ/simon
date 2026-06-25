import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useEventStreamContext } from '../context/EventStreamContext';

const SPARK_BARS = 20;
const HEALTH_POLL_MS = 5000;

export interface SparkBar {
  /** bar height in px (4–24) */
  h: number;
  /** animation delay in seconds, as a string for inline style */
  d: string;
}

export interface DerivedTelemetry {
  /** wall clock, ticks once per second */
  now: Date;
  /** frames/sec derived from frame-id deltas */
  fps: number;
  /** rolling sparkline of recent fps, mapped to bar heights */
  spark: SparkBar[];
  /** server uptime in seconds (polled from /api/health, interpolated between polls) */
  uptimeS: number;
}

/** Seed pattern so the sparkline looks alive before real samples accumulate. */
function seedSpark(): number[] {
  return Array.from({ length: SPARK_BARS }, (_, i) => 6 + Math.round(9 + 8 * Math.sin(i * 0.85)));
}

function toBars(history: number[]): SparkBar[] {
  const max = Math.max(...history, 1);
  const min = Math.min(...history);
  const span = max - min || 1;
  return history.map((v, i) => ({
    h: 4 + Math.round((20 * (v - min)) / span),
    d: ((i % SPARK_BARS) * 0.09).toFixed(2),
  }));
}

/**
 * Derives the time/throughput values the HUD shows that aren't carried on the
 * websocket: a live clock, fps (from `last_frame_id` deltas), a rolling
 * sparkline of that fps, and server uptime (polled from /api/health).
 */
export function useDerivedTelemetry(): DerivedTelemetry {
  const { last_frame_id } = useEventStreamContext();

  const [now, setNow] = useState<Date>(() => new Date());
  const [fps, setFps] = useState(0);
  const [spark, setSpark] = useState<SparkBar[]>(() => toBars(seedSpark()));
  const [uptimeS, setUptimeS] = useState(0);

  const frameRef = useRef(last_frame_id);
  const historyRef = useRef<number[]>(seedSpark());
  const haveRealRef = useRef(false);

  // keep the latest frame id available to the interval without re-subscribing
  useEffect(() => {
    frameRef.current = last_frame_id;
  }, [last_frame_id]);

  useEffect(() => {
    let prevFrame = frameRef.current;
    const tick = setInterval(() => {
      const cur = frameRef.current;
      const delta = Math.max(0, cur - prevFrame);
      prevFrame = cur;

      // Only fold real samples in once frames actually start advancing, so the
      // seed pattern persists until the pipeline is producing data.
      if (delta > 0) haveRealRef.current = true;
      if (haveRealRef.current) {
        const next = [...historyRef.current.slice(1), delta];
        historyRef.current = next;
        setFps(delta);
        setSpark(toBars(next));
      }

      setNow(new Date());
      setUptimeS((s) => s + 1);
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const h = await api.getHealth();
        if (!cancelled && typeof h.uptime_s === 'number') setUptimeS(h.uptime_s);
      } catch {
        // health endpoint unavailable - keep interpolating locally
      }
    }
    poll();
    const id = setInterval(poll, HEALTH_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return { now, fps, spark, uptimeS };
}
