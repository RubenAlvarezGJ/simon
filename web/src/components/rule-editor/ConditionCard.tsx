import type { Condition } from '../../lib/types';
import { categoryOf, zoneDotColor } from './constants';
import { conditionIsEmpty } from './summary';

export interface ZoneOption {
  value: string; // '' = any
  label: string;
}

interface Props {
  condition: Condition;
  index: number;
  canRemove: boolean;
  zoneOptions: ZoneOption[];
  onOpenClass: () => void;
  onZoneChange: (zone: string | null) => void;
  onRemove: () => void;
}

export function ConditionCard({ condition, index, canRemove, zoneOptions, onOpenClass, onZoneChange, onRemove }: Props) {
  const empty = conditionIsEmpty(condition);
  const cat = categoryOf(condition.class_name);
  const isThreat = cat === 'Threats';

  return (
    <div className={`cc-re-cond${empty ? ' incomplete' : ''}`}>
      <div className="cc-re-cond-head">
        <div className="cc-re-cond-head-left">
          <span className="cc-re-cond-num">{String(index + 1).padStart(2, '0')}</span>
          {empty && <span className="cc-re-cond-warn">needs at least one filter</span>}
        </div>
        <button className="cc-re-cond-remove" onClick={onRemove} disabled={!canRemove}>
          REMOVE
        </button>
      </div>

      <div className="cc-re-cond-grid">
        <div className="cc-re-field">
          <div className="cc-re-field-label">OBJECT</div>
          <button className="cc-re-object-btn" onClick={onOpenClass}>
            <span className="cc-re-object-btn-main">
              <span
                className={`cc-re-cat${isThreat ? ' threat' : ''}${condition.class_name ? '' : ' any'}`}
              >
                {condition.class_name ? cat.toUpperCase() : 'ANY'}
              </span>
              <span className={`cc-re-object-name${condition.class_name ? '' : ' placeholder'}`}>
                {condition.class_name ?? 'Any object'}
              </span>
            </span>
            <span className="cc-re-caret">▾</span>
          </button>
        </div>

        <div className="cc-re-field">
          <div className="cc-re-field-label">ZONE</div>
          <div className="cc-re-select-wrap">
            <span className="cc-re-zone-dot" style={{ background: zoneDotColor(condition.zone) }} />
            <select
              className={`cc-re-select${condition.zone ? '' : ' placeholder'}`}
              value={condition.zone ?? ''}
              onChange={(e) => onZoneChange(e.target.value || null)}
            >
              {zoneOptions.map((o) => (
                <option key={o.value || 'any'} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <span className="cc-re-caret cc-re-select-caret">▾</span>
          </div>
        </div>
      </div>
    </div>
  );
}
