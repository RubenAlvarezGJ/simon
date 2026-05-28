export type Point = [number, number];
export type Polygon = Point[];
export type ZonesMap = Record<string, Polygon>;

export interface Condition {
  class_name?: string | null;
  is_critical?: boolean | null;
  zone?: string | null;
  min_confidence?: number | null;
}

export interface Rule {
  name: string;
  description?: string;
  cooldown_seconds: number;
  conditions: Condition[];
}

export interface RulesPayload {
  rules: Rule[];
}

export interface ThreatSnapshot {
  tracker_id: number;
  class_name: string;
  is_critical: boolean;
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

export type CriticalClasses = string[];

export type WsEvent =
  | { type: 'hello'; data: { critical_classes: CriticalClasses; zones: ZonesMap; frame_shape: [number, number] | null; frame_id: number } }
  | { type: 'alert'; data: AlertPayload }
  | { type: 'snapshot'; data: { threats: ThreatSnapshot[]; pipeline_stats: PipelineStats; dispatcher_stats: DispatcherStats; frame_id: number } };
