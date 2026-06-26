import type { Mode } from './types';

interface GuideLine {
  key: string;
  text: string;
}

interface Guide {
  title: string;
  lines: GuideLine[];
}

const GUIDES: Record<Mode, Guide> = {
  view: {
    title: 'VIEW MODE',
    lines: [
      { key: 'CLICK', text: 'Select a zone to highlight it and reveal its vertices.' },
      { key: 'LIST', text: 'Use the panel above to jump between zones.' },
      { key: 'SAVE', text: 'Persist all changes to /api/zones.' },
    ],
  },
  draw: {
    title: 'DRAW MODE',
    lines: [
      { key: 'CLICK', text: 'Place a vertex. Minimum 3 to form a polygon.' },
      { key: 'DBL', text: 'Double-click anywhere to close and name the zone.' },
      { key: '3+', text: 'Dashed amber line previews the next edge.' },
    ],
  },
  edit: {
    title: 'EDIT MODE',
    lines: [
      { key: 'DRAG', text: 'Grab any vertex handle to reshape a zone.' },
      { key: 'R-CLK', text: 'Right-click a vertex to remove it (min 3 kept).' },
      { key: 'ALL', text: 'Every zone shows handles while editing.' },
    ],
  },
  delete: {
    title: 'DELETE MODE',
    lines: [
      { key: 'CLICK', text: 'Click inside a zone on the canvas to remove it.' },
      { key: 'DEL', text: 'Or use the DEL button on any list card.' },
      { key: 'SAVE', text: 'Deletions are local until you save.' },
    ],
  },
};

export function ZoneGuide({ mode }: { mode: Mode }) {
  const guide = GUIDES[mode];
  return (
    <div className="cc-ze-guide">
      <div className="cc-ze-guide-title">{guide.title}</div>
      <div className="cc-ze-guide-lines">
        {guide.lines.map((l) => (
          <div key={l.key} className="cc-ze-guide-line">
            <span className={`cc-ze-kbd${mode === 'delete' ? ' danger' : ''}`}>{l.key}</span>
            <span className="cc-ze-guide-text">{l.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
