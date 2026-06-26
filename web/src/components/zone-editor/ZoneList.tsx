import type { MouseEvent } from 'react';
import { polygonArea } from '../../lib/polygon';
import type { ZonesMap } from '../../lib/types';
import type { Mode } from './types';

interface Props {
  zones: ZonesMap;
  selected: string | null;
  mode: Mode;
  onSelect: (name: string) => void;
  onDelete: (name: string, e: MouseEvent) => void;
}

export function ZoneList({ zones, selected, mode, onSelect, onDelete }: Props) {
  const names = Object.keys(zones);
  const danger = mode === 'delete';

  return (
    <div className="cc-ze-list-panel">
      <div className="cc-ze-panel-head">
        <span className="cc-ze-panel-title">DEFINED ZONES</span>
        <span className="cc-ze-panel-meta">{names.length} TOTAL</span>
      </div>

      <div className="cc-ze-list">
        {names.map((name) => {
          const poly = zones[name];
          const sel = name === selected;
          const cls = [
            'cc-ze-card',
            sel ? 'selected' : '',
            danger ? 'danger' : '',
          ]
            .filter(Boolean)
            .join(' ');
          return (
            <div key={name} className={cls} onClick={() => onSelect(name)}>
              <div className="cc-ze-card-head">
                <span className="cc-ze-card-name">
                  <span className="cc-ze-card-swatch" />
                  <span className="cc-ze-card-title">{name}</span>
                </span>
                <button className="cc-ze-del" onClick={(e) => onDelete(name, e)}>
                  DEL
                </button>
              </div>
              <div className="cc-ze-card-meta">
                <span>{poly.length} pts</span>
                <span>{(polygonArea(poly) / 10000).toFixed(1)}k px²</span>
                {sel && <span className="cc-ze-card-sel">● SELECTED</span>}
              </div>
            </div>
          );
        })}

        {names.length === 0 && (
          <div className="cc-ze-empty">
            <div className="cc-ze-empty-glyph">⬡</div>
            <div className="cc-ze-empty-title">NO ZONES DEFINED</div>
            <div className="cc-ze-empty-sub">Switch to DRAW and click the snapshot to begin.</div>
          </div>
        )}
      </div>
    </div>
  );
}
