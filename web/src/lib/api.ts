import { z } from 'zod';
import type {
  CriticalClasses,
  HealthInfo,
  RulesPayload,
  SnapshotMeta,
  ZonesMap,
} from './types';

// ---- Zod schemas mirroring backend Pydantic ----

export const pointSchema = z.tuple([z.number().int().nonnegative(), z.number().int().nonnegative()]);
export const polygonSchema = z.array(pointSchema).min(3);
export const zonesSchema = z.record(z.string(), polygonSchema);

export const conditionSchema = z
  .object({
    class_name: z.string().optional().nullable(),
    is_critical: z.boolean().optional().nullable(),
    zone: z.string().optional().nullable(),
    min_confidence: z.number().min(0).max(1).optional().nullable(),
  })
  .refine(
    (c) =>
      c.class_name != null ||
      c.is_critical != null ||
      c.zone != null ||
      c.min_confidence != null,
    { message: 'At least one of class_name, is_critical, zone, min_confidence is required.' },
  );

export const ruleSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional().default(''),
  cooldown_seconds: z.number().min(0).default(30),
  conditions: z.array(conditionSchema).min(1),
});

export const rulesPayloadSchema = z.object({
  rules: z.array(ruleSchema).min(1),
});

// ---- HTTP helpers ----

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`${resp.status} ${resp.statusText} - ${text}`);
  }
  if (resp.status === 204) return undefined as unknown as T;
  return (await resp.json()) as T;
}

export const api = {
  getHealth: () => http<HealthInfo>('/api/health'),
  getCriticalClasses: () => http<CriticalClasses>('/api/critical-classes'),
  getState: () => http<unknown>('/api/state'),

  getZones: () => http<ZonesMap>('/api/zones'),
  putZones: (zones: ZonesMap) =>
    http<{ ok: boolean; zones: number }>('/api/zones', {
      method: 'PUT',
      body: JSON.stringify(zones),
    }),

  getRules: () => http<RulesPayload>('/api/rules'),
  putRules: (payload: RulesPayload) =>
    http<{ ok: boolean; rules: number }>('/api/rules', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getSnapshotMeta: () => http<SnapshotMeta>('/api/snapshot/meta'),
  snapshotUrl: (bust = true) =>
    `/api/snapshot.jpg${bust ? `?t=${Date.now()}` : ''}`,
};
