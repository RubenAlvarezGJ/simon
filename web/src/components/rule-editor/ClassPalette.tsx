import { useEffect, useRef, type KeyboardEvent } from 'react';
import { CATS, CLASS_OPTIONS, categoryOf } from './constants';

interface Props {
  current: string | null;
  search: string;
  onSearch: (v: string) => void;
  onPick: (cls: string | null) => void;
  onClose: () => void;
}

interface ItemRow {
  kind: 'item';
  name: string | null; // null = "Any object"
  category: string;
  selected: boolean;
}
interface HeaderRow {
  kind: 'header';
  label: string;
}
type Row = ItemRow | HeaderRow;

function buildRows(current: string | null, search: string): Row[] {
  const q = search.trim().toLowerCase();
  const item = (name: string | null): ItemRow => ({
    kind: 'item',
    name,
    category: name ? categoryOf(name).toUpperCase() : 'ANY',
    selected: name === null ? current == null : name === current,
  });

  if (q) {
    return CLASS_OPTIONS.filter((n) => n.includes(q)).map((n) => item(n));
  }

  const rows: Row[] = [item(null)];
  const placed = new Set<string>();
  for (const cat of CATS) {
    rows.push({ kind: 'header', label: cat.label.toUpperCase() });
    for (const n of cat.items) {
      placed.add(n);
      rows.push(item(n));
    }
  }
  const others = CLASS_OPTIONS.filter((n) => !placed.has(n));
  rows.push({ kind: 'header', label: 'OTHER OBJECTS' });
  for (const n of others) rows.push(item(n));
  return rows;
}

export function ClassPalette({ current, search, onSearch, onPick, onClose }: Props) {
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  const rows = buildRows(current, search);
  const empty = search.trim() !== '' && rows.length === 0;

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }

  return (
    <div className="cc-re-overlay" onMouseDown={onClose}>
      <div className="cc-re-palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="cc-re-palette-search">
          <span className="cc-re-palette-icon">⌕</span>
          <input
            ref={searchRef}
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search objects — person, car, handgun…"
          />
          <span className="cc-re-kbd-hint">ESC</span>
        </div>

        <div className="cc-re-palette-list">
          {rows.map((row, i) =>
            row.kind === 'header' ? (
              <div key={`h-${row.label}-${i}`} className="cc-re-palette-header">{row.label}</div>
            ) : (
              <button
                key={`i-${row.name ?? 'any'}-${i}`}
                className={`cc-re-palette-item${row.selected ? ' selected' : ''}`}
                onClick={() => onPick(row.name)}
              >
                <span className={`cc-re-cat${row.category === 'THREATS' ? ' threat' : ''}${row.name === null ? ' any' : ''}`}>
                  {row.category}
                </span>
                <span className="cc-re-palette-name">{row.name ?? 'Any object'}</span>
                {row.selected && <span className="cc-re-palette-check">● selected</span>}
              </button>
            ),
          )}
          {empty && (
            <div className="cc-re-palette-empty">No object matches “{search}”.</div>
          )}
        </div>
      </div>
    </div>
  );
}
