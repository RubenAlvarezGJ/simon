import type { Mode } from './types';

interface ModeDef {
  key: Mode;
  label: string;
  hint: string;
}

const MODES: ModeDef[] = [
  { key: 'view', label: 'VIEW', hint: 'inspect zones' },
  { key: 'draw', label: 'DRAW', hint: 'click to add points' },
  { key: 'edit', label: 'EDIT', hint: 'drag · right-click vertex' },
  { key: 'delete', label: 'DELETE', hint: 'click a zone' },
];

interface Props {
  mode: Mode;
  onMode: (m: Mode) => void;
  onRefresh: () => void;
  onSave: () => void;
}

export function ZoneToolbar({ mode, onMode, onRefresh, onSave }: Props) {
  return (
    <div className="cc-ze-toolbar">
      {MODES.map((m) => {
        const active = mode === m.key;
        const cls = [
          'cc-ze-mode',
          active ? 'active' : '',
          m.key === 'delete' ? 'danger' : '',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <button key={m.key} className={cls} onClick={() => onMode(m.key)}>
            <span className="cc-ze-mode-label">{m.label}</span>
            <span className="cc-ze-mode-hint">{m.hint}</span>
          </button>
        );
      })}
      <div className="cc-ze-toolbar-sep" />
      <button className="cc-ze-btn ghost" onClick={onRefresh}>
        ⟳ REFRESH
      </button>
      <button className="cc-ze-btn primary" onClick={onSave}>
        ↳ SAVE
      </button>
    </div>
  );
}
