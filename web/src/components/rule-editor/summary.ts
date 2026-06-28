import { Fragment, createElement, type ReactNode } from 'react';
import type { Condition, Rule } from '../../lib/types';
import { sevMeta } from './constants';

export function conditionIsEmpty(c: Condition): boolean {
  return c.class_name == null && c.zone == null && c.min_confidence == null;
}

// One human-readable clause per condition, e.g. `a person in zone "driveway"`.
export function summaryParts(rule: Rule): string[] {
  return rule.conditions.map((c) => {
    const obj = c.class_name ? `a ${c.class_name}` : 'any object';
    let loc = '';
    if (c.zone === 'global') loc = ' anywhere';
    else if (c.zone) loc = ` in zone "${c.zone}"`;
    const conf = c.min_confidence != null ? ` (≥${Math.round(c.min_confidence * 100)}%)` : '';
    return obj + loc + conf;
  });
}

export function summaryText(rule: Rule): string {
  const parts = summaryParts(rule);
  const body = parts.length ? parts.join(' and ') : 'any object';
  const verb = parts.length > 1 ? 'are detected' : 'is detected';
  return `When ${body} ${verb}, fire a ${rule.severity ?? 'high'} alert, then wait ${rule.cooldown_seconds}s before firing again.`;
}

// Highlighted plain-English sentence for the preview card.
export function previewNode(rule: Rule): ReactNode {
  const sev = sevMeta(rule.severity);
  const parts = summaryParts(rule);
  const seg: ReactNode[] = [];
  const muted = { color: '#6f7d89' };
  const strong = { color: '#eef3f7', fontWeight: 600 };

  seg.push(createElement('span', { key: 'w', style: muted }, 'When '));
  parts.forEach((p, idx) => {
    if (idx > 0) seg.push(createElement('span', { key: `and${idx}`, style: { ...muted, fontWeight: 600 } }, ' and '));
    seg.push(createElement('span', { key: `p${idx}`, style: strong }, p));
  });
  seg.push(createElement('span', { key: 'd', style: muted }, parts.length > 1 ? ' are detected, fire a ' : ' is detected, fire a '));
  seg.push(createElement('span', { key: 's', style: { color: sev.color, fontWeight: 700, letterSpacing: '.04em' } }, sev.label));
  seg.push(createElement('span', { key: 'c', style: muted }, ' alert, then wait '));
  seg.push(createElement('span', { key: 'cd', style: strong }, `${rule.cooldown_seconds}s`));
  seg.push(createElement('span', { key: 'e', style: muted }, ' before re-firing.'));

  return createElement(Fragment, null, seg);
}
