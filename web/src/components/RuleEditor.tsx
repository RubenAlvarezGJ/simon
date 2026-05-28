import { useEffect, useMemo, useState } from 'react';
import { api, rulesPayloadSchema } from '../lib/api';
import type { Condition, CriticalClasses, Rule, ZonesMap } from '../lib/types';

const BLANK_CONDITION: Condition = {
  class_name: null,
  is_critical: null,
  zone: null,
  min_confidence: null,
};

function blankRule(): Rule {
  return {
    name: '',
    description: '',
    cooldown_seconds: 30,
    conditions: [{ ...BLANK_CONDITION, is_critical: true }],
  };
}

export function RuleEditor() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [criticalClasses, setCriticalClasses] = useState<CriticalClasses>([]);
  const [zones, setZones] = useState<ZonesMap>({});
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [draft, setDraft] = useState<Rule>(blankRule());
  const [status, setStatus] = useState<string>('');

  useEffect(() => {
    void api.getRules()
      .then((rp) => setRules(rp.rules ?? []))
      .catch((err) => setStatus(`Rules load failed: ${err}`));
    void api.getCriticalClasses()
      .then(setCriticalClasses)
      .catch((err) => setStatus(`Critical-classes load failed: ${err}`));
    void api.getZones()
      .then(setZones)
      .catch((err) => setStatus(`Zones load failed: ${err}`));
  }, []);

  const zoneOptions = useMemo(() => ['global', ...Object.keys(zones)], [zones]);
  const classOptions = useMemo(() => criticalClasses, [criticalClasses]);

  function startEdit(i: number) {
    setEditIdx(i);
    setDraft(JSON.parse(JSON.stringify(rules[i])));
  }

  function startAdd() {
    setEditIdx(-1);
    setDraft(blankRule());
  }

  function cancelEdit() {
    setEditIdx(null);
    setDraft(blankRule());
  }

  function commitDraft() {
    const next = rules.slice();
    if (editIdx === null) return;
    if (editIdx === -1) next.push(draft);
    else next[editIdx] = draft;
    setRules(next);
    setEditIdx(null);
    setDraft(blankRule());
  }

  function deleteRule(i: number) {
    const next = rules.slice();
    next.splice(i, 1);
    setRules(next);
  }

  async function save() {
    try {
      const payload = { rules };
      rulesPayloadSchema.parse(payload);
      await api.putRules(payload);
      setStatus(`Saved ${rules.length} rule(s).`);
    } catch (err) {
      setStatus(`Validation/save failed: ${err}`);
    }
  }

  return (
    <div className="panel rule-editor">
      <div className="editor-toolbar">
        <h3>Rules</h3>
        <button onClick={startAdd}>Add rule</button>
        <button onClick={() => void save()} disabled={rules.length === 0}>Save</button>
        <span className="muted">{status}</span>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Cooldown</th>
            <th>Conditions</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r, i) => (
            <tr key={`${r.name}-${i}`}>
              <td><strong>{r.name}</strong>{r.description && <div className="muted">{r.description}</div>}</td>
              <td>{r.cooldown_seconds}s</td>
              <td>
                {r.conditions.map((c, j) => (
                  <div key={j} className="cond-row">
                    {summariseCondition(c)}
                  </div>
                ))}
              </td>
              <td>
                <button onClick={() => startEdit(i)}>Edit</button>
                <button onClick={() => deleteRule(i)}>Delete</button>
              </td>
            </tr>
          ))}
          {rules.length === 0 && (
            <tr><td colSpan={4} className="muted">No rules yet.</td></tr>
          )}
        </tbody>
      </table>

      {editIdx !== null && (
        <RuleForm
          rule={draft}
          onChange={setDraft}
          classOptions={classOptions}
          zoneOptions={zoneOptions}
          onCommit={commitDraft}
          onCancel={cancelEdit}
        />
      )}
    </div>
  );
}

function summariseCondition(c: Condition): string {
  const parts: string[] = [];
  if (c.class_name) parts.push(`class=${c.class_name}`);
  if (c.is_critical != null) parts.push(`is_critical=${c.is_critical}`);
  if (c.zone) parts.push(`zone=${c.zone}`);
  if (c.min_confidence != null) parts.push(`conf>=${c.min_confidence}`);
  return parts.join(', ') || '(empty)';
}

interface FormProps {
  rule: Rule;
  onChange: (r: Rule) => void;
  classOptions: string[];
  zoneOptions: string[];
  onCommit: () => void;
  onCancel: () => void;
}

function RuleForm({ rule, onChange, classOptions, zoneOptions, onCommit, onCancel }: FormProps) {
  function setCondition(i: number, patch: Partial<Condition>) {
    const next = rule.conditions.slice();
    next[i] = { ...next[i], ...patch };
    onChange({ ...rule, conditions: next });
  }
  function addCondition() {
    onChange({ ...rule, conditions: [...rule.conditions, { ...BLANK_CONDITION, is_critical: true }] });
  }
  function removeCondition(i: number) {
    const next = rule.conditions.slice();
    next.splice(i, 1);
    onChange({ ...rule, conditions: next });
  }

  return (
    <div className="modal-card">
      <h4>{rule.name ? `Edit "${rule.name}"` : 'New rule'}</h4>
      <label>
        Name
        <input
          value={rule.name}
          onChange={(e) => onChange({ ...rule, name: e.target.value })}
        />
      </label>
      <label>
        Description
        <input
          value={rule.description ?? ''}
          onChange={(e) => onChange({ ...rule, description: e.target.value })}
        />
      </label>
      <label>
        Cooldown seconds
        <input
          type="number"
          min={0}
          step={1}
          value={rule.cooldown_seconds}
          onChange={(e) => onChange({ ...rule, cooldown_seconds: Number(e.target.value) })}
        />
      </label>

      <h5>Conditions (ALL must match)</h5>
      <ul className="cond-list">
        {rule.conditions.map((c, i) => (
          <li key={i} className="cond-edit">
            <label>
              Class
              <input
                list={`class-options-${i}`}
                value={c.class_name ?? ''}
                onChange={(e) => setCondition(i, { class_name: e.target.value || null })}
                placeholder="(any)"
              />
              <datalist id={`class-options-${i}`}>
                {classOptions.map((cn) => (
                  <option key={cn} value={cn} />
                ))}
              </datalist>
            </label>
            <label>
              Critical
              <select
                value={c.is_critical == null ? '' : c.is_critical ? 'true' : 'false'}
                onChange={(e) =>
                  setCondition(i, {
                    is_critical:
                      e.target.value === '' ? null : e.target.value === 'true',
                  })
                }
              >
                <option value="">(any)</option>
                <option value="true">critical</option>
                <option value="false">non-critical</option>
              </select>
            </label>
            <label>
              Zone
              <select
                value={c.zone ?? ''}
                onChange={(e) => setCondition(i, { zone: e.target.value || null })}
              >
                <option value="">(any)</option>
                {zoneOptions.map((z) => (
                  <option key={z} value={z}>{z}</option>
                ))}
              </select>
            </label>
            <label>
              Min conf
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={c.min_confidence ?? ''}
                onChange={(e) => setCondition(i, {
                  min_confidence: e.target.value === '' ? null : Number(e.target.value),
                })}
              />
            </label>
            <button onClick={() => removeCondition(i)} disabled={rule.conditions.length === 1}>x</button>
          </li>
        ))}
      </ul>
      <button onClick={addCondition}>Add condition</button>
      <div className="modal-actions">
        <button onClick={onCommit} disabled={!rule.name.trim() || rule.conditions.length === 0}>OK</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
