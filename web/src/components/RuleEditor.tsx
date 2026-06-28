import { useEffect, useMemo, useState } from 'react';
import { api, rulesPayloadSchema } from '../lib/api';
import type { Condition, Rule, Severity, ZonesMap } from '../lib/types';
import { RuleList } from './rule-editor/RuleList';
import { RuleDetail } from './rule-editor/RuleDetail';
import { ClassPalette } from './rule-editor/ClassPalette';
import type { ZoneOption } from './rule-editor/ConditionCard';
import { prettyZone } from './rule-editor/constants';
import { conditionIsEmpty } from './rule-editor/summary';
import type { EditorStatus } from './rule-editor/types';

const BLANK_CONDITION: Condition = { class_name: null, zone: null, min_confidence: null };

function blankRule(): Rule {
  return { name: '', description: '', severity: 'high', cooldown_seconds: 30, conditions: [{ ...BLANK_CONDITION }] };
}

function rulesValid(rules: Rule[]): boolean {
  return (
    rules.length > 0 &&
    rules.every((r) => r.name.trim() !== '' && r.conditions.length > 0 && r.conditions.every((c) => !conditionIsEmpty(c)))
  );
}

export function RuleEditor() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [zones, setZones] = useState<ZonesMap>({});
  const [selected, setSelected] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState<EditorStatus>({ text: 'Loading rules from /api/rules…', kind: 'pending' });
  const [pickerFor, setPickerFor] = useState<number | null>(null);
  const [classSearch, setClassSearch] = useState('');

  useEffect(() => {
    void loadRules();
    void api
      .getZones()
      .then(setZones)
      .catch((err) => setStatus({ text: `Zones load failed: ${err}`, kind: 'err' }));
  }, []);

  async function loadRules() {
    try {
      const rp = await api.getRules();
      const loaded = rp.rules ?? [];
      setRules(loaded);
      setSelected(loaded.length ? 0 : null);
      setDirty(false);
      setStatus({ text: `Loaded ${loaded.length} rule(s) from /api/rules.`, kind: 'ok' });
    } catch (err) {
      setStatus({ text: `Rules load failed: ${err}`, kind: 'err' });
    }
  }

  const zoneOptions = useMemo<ZoneOption[]>(
    () => [
      { value: '', label: 'Any zone' },
      { value: 'global', label: 'Global · anywhere' },
      ...Object.keys(zones).map((z) => ({ value: z, label: prettyZone(z) })),
    ],
    [zones],
  );

  const selectedRule = selected != null ? rules[selected] ?? null : null;
  const valid = rulesValid(rules);

  // ---- mutations (selected rule mutated in place) ----
  function patchRule(patch: Partial<Rule>) {
    setRules((cur) => {
      if (selected == null || !cur[selected]) return cur;
      const next = cur.slice();
      next[selected] = { ...next[selected], ...patch };
      return next;
    });
    setDirty(true);
  }

  function patchCondition(i: number, patch: Partial<Condition>) {
    setRules((cur) => {
      if (selected == null || !cur[selected]) return cur;
      const next = cur.slice();
      const r = { ...next[selected] };
      const conds = r.conditions.slice();
      conds[i] = { ...conds[i], ...patch };
      r.conditions = conds;
      next[selected] = r;
      return next;
    });
    setDirty(true);
  }

  function addCondition() {
    setRules((cur) => {
      if (selected == null || !cur[selected]) return cur;
      const next = cur.slice();
      const r = { ...next[selected] };
      r.conditions = [...r.conditions, { ...BLANK_CONDITION }];
      next[selected] = r;
      return next;
    });
    setDirty(true);
  }

  function removeCondition(i: number) {
    setRules((cur) => {
      if (selected == null || !cur[selected]) return cur;
      const r = cur[selected];
      if (r.conditions.length <= 1) return cur;
      const next = cur.slice();
      next[selected] = { ...r, conditions: r.conditions.filter((_, j) => j !== i) };
      return next;
    });
    setDirty(true);
  }

  function addRule() {
    setRules((cur) => {
      const next = [...cur, blankRule()];
      setSelected(next.length - 1);
      return next;
    });
    setDirty(true);
    setStatus({ text: 'New rule drafted — give it a name and a condition.', kind: 'pending' });
  }

  function deleteSelected() {
    if (selected == null) return;
    setRules((cur) => {
      const name = cur[selected]?.name || 'untitled';
      const next = cur.filter((_, j) => j !== selected);
      setSelected(next.length === 0 ? null : Math.max(0, selected - 1));
      setStatus({ text: `Deleted rule "${name}". Save to persist.`, kind: 'err' });
      return next;
    });
    setDirty(true);
  }

  // ---- class picker ----
  function pickClass(cls: string | null) {
    if (pickerFor == null) return;
    patchCondition(pickerFor, { class_name: cls });
    setPickerFor(null);
    setClassSearch('');
  }

  // ---- save / revert ----
  async function save() {
    try {
      const payload = { rules };
      rulesPayloadSchema.parse(payload);
      await api.putRules(payload);
      setDirty(false);
      setStatus({ text: `Saved ${rules.length} rule(s) → PUT /api/rules · 200 OK.`, kind: 'ok' });
    } catch (err) {
      setStatus({ text: `Save failed: ${err}`, kind: 'err' });
    }
  }

  async function revert() {
    await loadRules();
  }

  return (
    <main className="cc-re-main">
      <RuleList rules={rules} selected={selected} onSelect={setSelected} onAdd={addRule} />

      <RuleDetail
        rule={selectedRule}
        zoneOptions={zoneOptions}
        status={status}
        dirty={dirty}
        valid={valid}
        showPreview
        onName={(v) => patchRule({ name: v })}
        onDesc={(v) => patchRule({ description: v })}
        onSeverity={(s: Severity) => patchRule({ severity: s })}
        onCooldown={(v) => patchRule({ cooldown_seconds: v })}
        onAddCondition={addCondition}
        onRemoveCondition={removeCondition}
        onZoneChange={(i, zone) => patchCondition(i, { zone })}
        onOpenClass={(i) => {
          setPickerFor(i);
          setClassSearch('');
        }}
        onDelete={deleteSelected}
        onRevert={() => void revert()}
        onSave={() => void save()}
        onAdd={addRule}
      />

      {pickerFor != null && (
        <ClassPalette
          current={selectedRule?.conditions[pickerFor]?.class_name ?? null}
          search={classSearch}
          onSearch={setClassSearch}
          onPick={pickClass}
          onClose={() => {
            setPickerFor(null);
            setClassSearch('');
          }}
        />
      )}
    </main>
  );
}
