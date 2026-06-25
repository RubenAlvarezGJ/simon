// Display formatters shared across the HUD.

const DAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

export function formatClock(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function formatDate(d: Date): string {
  return `${DAYS[d.getDay()]} ${pad(d.getDate())} ${MONTHS[d.getMonth()]}`;
}

/** Seconds -> hh:mm:ss (used for uptime). */
export function formatUptime(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

/** Seconds -> "12s" / "2m 04s" (tracked-object age). */
export function formatAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${pad(s % 60)}s`;
}

/** Epoch-seconds timestamp -> "8s ago" / "5m ago" / "2h ago". */
export function timeAgo(triggeredAt: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - triggeredAt));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

/** Numeric stat formatter: integers grouped, floats to 1-2 dp, nullish -> "-". */
export function num(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    if (v % 1 === 0) return v.toLocaleString('en-US');
    return v.toFixed(v >= 100 ? 1 : 2);
  }
  return '-';
}
