import type { Rule } from '../../lib/types';
import { sevMeta } from './constants';
import { conditionIsEmpty, summaryText } from './summary';

interface Props {
  rules: Rule[];
  selected: number | null;
  onSelect: (i: number) => void;
  onAdd: () => void;
}

export function RuleList({ rules, selected, onSelect, onAdd }: Props) {
  return (
    <div className="cc-re-col-left">
      <button className="cc-re-add" onClick={onAdd}>
        <span className="cc-re-add-plus">+</span> NEW RULE
      </button>

      <div className="cc-re-list-panel">
        <div className="cc-re-panel-head">
          <span className="cc-re-panel-title">DETECTION RULES</span>
          <span className="cc-re-panel-meta">{rules.length} ACTIVE</span>
        </div>

        <div className="cc-re-list">
          {rules.map((r, i) => {
            const sev = sevMeta(r.severity);
            const invalid = !r.name.trim() || r.conditions.some(conditionIsEmpty);
            const condStr = `${r.conditions.length} ${r.conditions.length === 1 ? 'COND' : 'CONDS'}`;
            return (
              <div
                key={i}
                className={`cc-re-card${i === selected ? ' selected' : ''}`}
                style={{ borderLeftColor: sev.color }}
                onClick={() => onSelect(i)}
              >
                <div className="cc-re-card-head">
                  <span className={`cc-re-card-name${r.name ? '' : ' placeholder'}`}>
                    {r.name || 'untitled_rule'}
                  </span>
                  <span className="cc-re-sev-pill" style={{ color: sev.color, background: sev.bg }}>
                    {sev.label}
                  </span>
                </div>
                <div className="cc-re-card-summary">{summaryText(r)}</div>
                <div className="cc-re-card-meta">
                  <span>{condStr}</span>
                  <span>CD {r.cooldown_seconds}s</span>
                  {invalid && <span className="cc-re-card-warn">⚠ INCOMPLETE</span>}
                </div>
              </div>
            );
          })}

          {rules.length === 0 && (
            <div className="cc-re-empty">
              <div className="cc-re-empty-glyph">◇</div>
              <div className="cc-re-empty-title">NO RULES DEFINED</div>
              <div className="cc-re-empty-sub">
                Add a rule to start firing alerts
                <br />
                when the detector sees a match.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
