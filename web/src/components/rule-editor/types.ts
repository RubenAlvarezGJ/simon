export interface EditorStatus {
  text: string;
  kind: 'ok' | 'pending' | 'err';
}

export const STATUS_DOT: Record<EditorStatus['kind'], string> = {
  ok: 'var(--ok)',
  pending: 'var(--warn)',
  err: 'var(--bad)',
};
