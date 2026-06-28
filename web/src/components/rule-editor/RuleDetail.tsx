import type { Rule, Severity } from '../../lib/types';
import { COOLDOWN_PRESETS, SEVERITY_ORDER, SEV, cooldownLabel, sevMeta } from './constants';
import { previewNode } from './summary';
import { ConditionCard, type ZoneOption } from './ConditionCard';
import { STATUS_DOT, type EditorStatus } from './types';

interface Props {
  rule: Rule | null;
  zoneOptions: ZoneOption[];
  status: EditorStatus;
  dirty: boolean;
  valid: boolean;
  showPreview: boolean;
  onName: (v: string) => void;
  onDesc: (v: string) => void;
  onSeverity: (s: Severity) => void;
  onCooldown: (v: number) => void;
  onAddCondition: () => void;
  onRemoveCondition: (i: number) => void;
  onZoneChange: (i: number, zone: string | null) => void;
  onOpenClass: (i: number) => void;
  onDelete: () => void;
  onRevert: () => void;
  onSave: () => void;
  onAdd: () => void;
}

export function RuleDetail(props: Props) {
  const { rule } = props;

  if (!rule) {
    return (
      <div className="cc-re-detail">
        <div className="cc-re-noselect">
          <div className="cc-re-noselect-glyph">◇</div>
          <div className="cc-re-noselect-title">NO RULE SELECTED</div>
          <div className="cc-re-noselect-sub">
            Pick a rule from the list, or create a new one
            <br />
            to configure its detection conditions.
          </div>
          <button className="cc-re-noselect-add" onClick={props.onAdd}>
            + NEW RULE
          </button>
        </div>
      </div>
    );
  }

  const sev = sevMeta(rule.severity);

  return (
    <div className="cc-re-detail">
      <div className="cc-re-detail-body">
        {/* name + delete */}
        <div className="cc-re-name-row">
          <div className="cc-re-name-fields">
            <div className="cc-re-field-label spaced">RULE NAME</div>
            <input
              className="cc-re-name-input"
              value={rule.name}
              onChange={(e) => props.onName(e.target.value)}
              placeholder="e.g. intruder_in_driveway"
            />
            <input
              className="cc-re-desc-input"
              value={rule.description ?? ''}
              onChange={(e) => props.onDesc(e.target.value)}
              placeholder="Short description of what this rule watches for…"
            />
          </div>
          <button className="cc-re-delete" onClick={props.onDelete}>
            DELETE
          </button>
        </div>

        {/* severity + cooldown */}
        <div className="cc-re-sev-cd">
          <div>
            <div className="cc-re-field-label spaced">SEVERITY</div>
            <div className="cc-re-sev-options">
              {SEVERITY_ORDER.map((k) => {
                const meta = SEV[k];
                const active = (rule.severity ?? 'high') === k;
                return (
                  <button
                    key={k}
                    className={`cc-re-sev-opt${active ? ' active' : ''}`}
                    style={active ? { background: meta.bg, borderColor: meta.color } : undefined}
                    onClick={() => props.onSeverity(k)}
                  >
                    <span
                      className="cc-re-sev-dot"
                      style={{ background: meta.color, boxShadow: active ? `0 0 8px ${meta.color}` : 'none' }}
                    />
                    <span className="cc-re-sev-label" style={active ? { color: meta.color } : undefined}>
                      {meta.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="cc-re-field-label spaced">COOLDOWN</div>
            <div className="cc-re-cd-row">
              <div className="cc-re-cd-input-wrap">
                <input
                  className="cc-re-cd-input"
                  value={String(rule.cooldown_seconds)}
                  inputMode="numeric"
                  onChange={(e) => {
                    const v = parseInt(e.target.value.replace(/[^0-9]/g, ''), 10);
                    props.onCooldown(Number.isNaN(v) ? 0 : v);
                  }}
                />
                <span className="cc-re-cd-unit">sec</span>
              </div>
              <div className="cc-re-cd-presets">
                {COOLDOWN_PRESETS.map((v) => (
                  <button
                    key={v}
                    className={`cc-re-cd-preset${rule.cooldown_seconds === v ? ' active' : ''}`}
                    onClick={() => props.onCooldown(v)}
                  >
                    {cooldownLabel(v)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* preview */}
        {props.showPreview && (
          <div className="cc-re-preview">
            <div className="cc-re-preview-bar" style={{ background: sev.color }} />
            <div className="cc-re-preview-head">
              <span className="cc-re-preview-dot" style={{ background: sev.color }} />
              <span className="cc-re-preview-label">PREVIEW</span>
            </div>
            <div className="cc-re-preview-text">{previewNode(rule)}</div>
          </div>
        )}

        {/* conditions */}
        <div className="cc-re-conds">
          <div className="cc-re-conds-head">
            <div>
              <div className="cc-re-panel-title">MATCH CONDITIONS</div>
              <div className="cc-re-conds-sub">All conditions must be true in the same frame to fire.</div>
            </div>
            <button className="cc-re-add-cond" onClick={props.onAddCondition}>
              + CONDITION
            </button>
          </div>

          <div className="cc-re-cond-list">
            {rule.conditions.map((c, i) => (
              <ConditionCard
                key={i}
                condition={c}
                index={i}
                canRemove={rule.conditions.length > 1}
                zoneOptions={props.zoneOptions}
                onOpenClass={() => props.onOpenClass(i)}
                onZoneChange={(zone) => props.onZoneChange(i, zone)}
                onRemove={() => props.onRemoveCondition(i)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* status / save bar */}
      <div className="cc-re-savebar">
        <span className="cc-re-status-dot" style={{ background: STATUS_DOT[props.status.kind] }} />
        <span className="cc-re-status-text">{props.status.text}</span>
        <span className={`cc-re-dirty${props.dirty ? ' on' : ''}`}>
          {props.dirty ? 'UNSAVED CHANGES' : 'ALL SAVED'}
        </span>
        <button className="cc-re-btn ghost" onClick={props.onRevert}>
          REVERT
        </button>
        <button className="cc-re-btn primary" onClick={props.onSave} disabled={!props.valid}>
          SAVE ALL
        </button>
      </div>
    </div>
  );
}
