export type Point = [number, number];
export type Polygon = Point[];
export type ZonesMap = Record<string, Polygon>;

export type Severity = 'low' | 'high' | 'critical';

export interface Condition {
  class_name?: string | null;
  zone?: string | null;
  min_confidence?: number | null;
}

export interface Rule {
  name: string;
  description?: string;
  severity?: Severity;
  cooldown_seconds: number;
  conditions: Condition[];
}

export interface RulesPayload {
  rules: Rule[];
}

export interface ThreatSnapshot {
  tracker_id: number;
  class_name: string;
  status: string;
  frame_count: number;
  confidence: number;
  bbox: number[];
  age_seconds: number;
  alert_fired: boolean;
  active_zones: string[];
  first_seen_at: number;
  last_seen_at: number;
}

export interface AlertPayload {
  rule_name: string;
  severity: Severity;
  triggered_at: number;
  tracker_ids: number[];
  threat_snapshots: ThreatSnapshot[];
  rule_description: string;
}

export interface PipelineStats {
  reader_frames_read?: number;
  reader_frames_dropped?: number;
  engine_frames_processed?: number;
  engine_frames_skipped?: number;
  engine_avg_inference_ms?: number;
  [k: string]: unknown;
}

export interface DispatcherStats {
  enqueued?: number;
  delivered?: number;
  dropped?: number;
  sink_errors?: number;
  [k: string]: unknown;
}

export interface SnapshotMeta {
  width: number;
  height: number;
  frame_id: number;
}

export interface HealthInfo {
  status: string;
  uptime_s: number;
  pipeline_running: boolean;
  frame_id: number;
}

export type WsEvent =
  | { type: 'hello'; data: { severities: Severity[]; zones: ZonesMap; frame_shape: [number, number] | null; frame_id: number } }
  | { type: 'alert'; data: AlertPayload }
  | { type: 'snapshot'; data: { threats: ThreatSnapshot[]; pipeline_stats: PipelineStats; dispatcher_stats: DispatcherStats; frame_id: number } };
