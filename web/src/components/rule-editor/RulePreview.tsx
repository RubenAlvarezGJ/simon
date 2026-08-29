import { useEffect, type KeyboardEvent } from 'react';
import type { Rule } from '../../lib/types';
import { sevMeta } from './constants';
import { previewNode } from './summary';

interface Props {
  rule: Rule;
  onClose: () => void;
}

export function RulePreview({ rule, onClose }: Props) {
  const sev = sevMeta(rule.severity);

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function onPanelKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }

  return (
    <div className="cc-re-overlay cc-re-overlay-center" onMouseDown={onClose}>
      <div className="cc-re-preview cc-re-preview-modal" onMouseDown={(e) => e.stopPropagation()} onKeyDown={onPanelKey}>
        <div className="cc-re-preview-bar" style={{ background: sev.color }} />
        <div className="cc-re-preview-head">
          <span className="cc-re-preview-dot" style={{ background: sev.color }} />
          <span className="cc-re-preview-label">PREVIEW</span>
          <span className="cc-re-kbd-hint">ESC</span>
        </div>
        <div className="cc-re-preview-text">{previewNode(rule)}</div>
      </div>
    </div>
  );
}
