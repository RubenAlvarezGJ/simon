export type Mode = 'view' | 'draw' | 'edit' | 'delete';

export type StatusKind = 'ok' | 'pending' | 'err';

export interface EditorStatus {
  text: string;
  kind: StatusKind;
}

export interface DragState {
  zone: string;
  vertexIdx: number;
}
