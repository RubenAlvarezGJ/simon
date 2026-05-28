import { useEffect, useRef, useState } from 'react';
import type {
  AlertPayload,
  CriticalClasses,
  DispatcherStats,
  PipelineStats,
  ThreatSnapshot,
  WsEvent,
  ZonesMap,
} from '../lib/types';

export interface EventStreamState {
  connected: boolean;
  hello: {
    critical_classes: CriticalClasses;
    zones: ZonesMap;
    frame_shape: [number, number] | null;
    frame_id: number;
  } | null;
  threats: ThreatSnapshot[];
  pipeline_stats: PipelineStats;
  dispatcher_stats: DispatcherStats;
  recent_alerts: AlertPayload[];
  last_frame_id: number;
}

const MAX_ALERTS = 100;
const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 15_000;

function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/events`;
}

export function useEventStream(): EventStreamState {
  const [state, setState] = useState<EventStreamState>({
    connected: false,
    hello: null,
    threats: [],
    pipeline_stats: {},
    dispatcher_stats: {},
    recent_alerts: [],
    last_frame_id: 0,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByCleanupRef = useRef(false);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        backoffRef.current = INITIAL_BACKOFF_MS;
        setState((s) => ({ ...s, connected: true }));
      };

      ws.onmessage = (ev) => {
        let msg: WsEvent;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        setState((s) => {
          switch (msg.type) {
            case 'hello':
              return { ...s, hello: msg.data, last_frame_id: msg.data.frame_id };
            case 'snapshot':
              return {
                ...s,
                threats: msg.data.threats,
                pipeline_stats: msg.data.pipeline_stats,
                dispatcher_stats: msg.data.dispatcher_stats,
                last_frame_id: msg.data.frame_id,
              };
            case 'alert':
              return {
                ...s,
                recent_alerts: [msg.data, ...s.recent_alerts].slice(0, MAX_ALERTS),
              };
            default:
              return s;
          }
        });
      };

      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (closedByCleanupRef.current) return;
        const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
        timeoutRef.current = setTimeout(connect, delay);
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      };

      ws.onerror = () => {
        // Let onclose handle reconnect logic.
      };
    }

    closedByCleanupRef.current = false;
    connect();

    return () => {
      closedByCleanupRef.current = true;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      wsRef.current?.close();
    };
  }, []);

  return state;
}
