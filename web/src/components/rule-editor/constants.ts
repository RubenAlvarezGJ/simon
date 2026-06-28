import type { Severity } from '../../lib/types';

// Full COCO class list + the custom `handgun` class, in the order the picker shows them.
export const CLASS_OPTIONS: string[] = [
  'person',
  'bicycle',
  'car',
  'motorcycle',
  'airplane',
  'bus',
  'train',
  'truck',
  'boat',
  'traffic light',
  'fire hydrant',
  'stop sign',
  'parking meter',
  'bench',
  'bird',
  'cat',
  'dog',
  'horse',
  'sheep',
  'cow',
  'elephant',
  'bear',
  'zebra',
  'giraffe',
  'backpack',
  'umbrella',
  'handbag',
  'tie',
  'suitcase',
  'frisbee',
  'skis',
  'snowboard',
  'sports ball',
  'kite',
  'baseball bat',
  'baseball glove',
  'skateboard',
  'surfboard',
  'tennis racket',
  'bottle',
  'wine glass',
  'cup',
  'fork',
  'knife',
  'spoon',
  'bowl',
  'banana',
  'apple',
  'sandwich',
  'orange',
  'broccoli',
  'carrot',
  'hot dog',
  'pizza',
  'donut',
  'cake',
  'chair',
  'couch',
  'potted plant',
  'bed',
  'dining table',
  'toilet',
  'tv',
  'laptop',
  'mouse',
  'remote',
  'keyboard',
  'cell phone',
  'microwave',
  'oven',
  'toaster',
  'sink',
  'refrigerator',
  'book',
  'clock',
  'vase',
  'scissors',
  'teddy bear',
  'hair drier',
  'toothbrush',
  'handgun',
];

// Category groups surfaced in the class palette (matches the Config Editor design).
export interface ClassCategory {
  label: string;
  items: string[];
}

export const CATS: ClassCategory[] = [
  { label: 'People', items: ['person'] },
  { label: 'Threats', items: ['handgun', 'knife', 'baseball bat', 'scissors'] },
  { label: 'Vehicles', items: ['bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat'] },
  { label: 'Animals', items: ['bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe'] },
  { label: 'Bags & carry', items: ['backpack', 'umbrella', 'handbag', 'tie', 'suitcase'] },
  { label: 'Street', items: ['traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench'] },
];

export function categoryOf(cls: string | null | undefined): string {
  if (!cls) return 'Object';
  const c = CATS.find((k) => k.items.includes(cls));
  return c ? c.label : 'Object';
}

// Severity metadata — colors mirror the --ok/--warn/--bad tokens used elsewhere.
export interface SeverityMeta {
  label: string;
  color: string;
  bg: string;
}

export const SEV: Record<Severity, SeverityMeta> = {
  low: { label: 'LOW', color: '#58c7ef', bg: 'rgba(88,199,239,.12)' },
  high: { label: 'HIGH', color: '#ffb020', bg: 'rgba(255,176,32,.12)' },
  critical: { label: 'CRITICAL', color: '#ff4d4d', bg: 'rgba(255,77,77,.12)' },
};

export function sevMeta(sev: Severity | undefined): SeverityMeta {
  return SEV[sev ?? 'high'];
}

export const SEVERITY_ORDER: Severity[] = ['low', 'high', 'critical'];

export const COOLDOWN_PRESETS: number[] = [10, 30, 60, 120, 300];

export function cooldownLabel(v: number): string {
  return v >= 60 ? `${v / 60}m` : `${v}s`;
}

// Deterministic accent dot for a zone name (real zones carry no color of their own).
const ZONE_DOT_PALETTE = ['#2fd6ff', '#ffb020', '#b48cff', '#38e08a', '#ff7ab0', '#7fd9f0'];

export function zoneDotColor(zone: string | null | undefined): string {
  if (!zone) return '#5d6b78';
  if (zone === 'global') return '#38e08a';
  let hash = 0;
  for (let i = 0; i < zone.length; i += 1) hash = (hash * 31 + zone.charCodeAt(i)) | 0;
  return ZONE_DOT_PALETTE[Math.abs(hash) % ZONE_DOT_PALETTE.length];
}

export function prettyZone(z: string): string {
  return z.replace(/_/g, ' ');
}
