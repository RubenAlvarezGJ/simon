import type { MouseEvent, RefObject } from 'react';
import type { Point, Polygon, SnapshotMeta, ZonesMap } from '../../lib/types';
import type { Mode } from './types';

interface Props {
  svgRef: RefObject<SVGSVGElement | null>;
  inputRef: RefObject<HTMLInputElement | null>;
  meta: SnapshotMeta | null;
  snapshotUrl: string;
  zones: ZonesMap;
  mode: Mode;
  selected: string | null;
  pending: Polygon | null;
  cursor: Point;
  naming: boolean;
  nameInput: string;
  onBgDown: (e: MouseEvent) => void;
  onMove: (e: MouseEvent) => void;
  onUp: () => void;
  onDbl: () => void;
  onPolyClick: (name: string) => void;
  onVertexDown: (name: string, idx: number, e: MouseEvent) => void;
  onNameInput: (v: string) => void;
  onNameKey: (e: React.KeyboardEvent) => void;
  onConfirmName: () => void;
  onCancelName: () => void;
}

function pad4(n: number): string {
  return String(n).padStart(4, '0');
}

export function ZoneCanvas({
  svgRef,
  inputRef,
  meta,
  snapshotUrl,
  zones,
  mode,
  selected,
  pending,
  cursor,
  naming,
  nameInput,
  onBgDown,
  onMove,
  onUp,
  onDbl,
  onPolyClick,
  onVertexDown,
  onNameInput,
  onNameKey,
  onConfirmName,
  onCancelName,
}: Props) {
  const vbW = meta?.width ?? 1920;
  const vbH = meta?.height ?? 1080;
  const labelFont = Math.max(12, Math.round(vbH / 48));
  const vertexR = Math.max(3, Math.round(vbH / 200));
  const danger = mode === 'delete';
  const names = Object.keys(zones);
  const polyEvents = mode === 'view' || mode === 'delete';
  const showHandlesFor = (name: string) => mode === 'edit' || name === selected;

  return (
    <div className="cc-ze-canvas">
      <div className="cc-ze-stage">
        {/* backdrop */}
        {snapshotUrl ? (
          <img className="cc-ze-snapshot" src={snapshotUrl} alt="" draggable={false} />
        ) : (
          <>
            <div className="cc-ze-snapshot-fallback" />
            <div className="cc-ze-snapshot-grid" />
            <div className="cc-ze-snapshot-empty">
              <div className="l1">[ SNAPSHOT ]</div>
              <div className="l2">/api/snapshot.jpg</div>
            </div>
          </>
        )}

        {/* SVG editor surface */}
        <svg
          ref={svgRef}
          className="cc-ze-svg"
          viewBox={`0 0 ${vbW} ${vbH}`}
          preserveAspectRatio="none"
          style={{ cursor: mode === 'draw' ? 'crosshair' : 'default' }}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onUp}
          onDoubleClick={onDbl}
          onContextMenu={(e) => e.preventDefault()}
        >
          <rect
            x={0}
            y={0}
            width={vbW}
            height={vbH}
            fill="transparent"
            pointerEvents="all"
            onMouseDown={onBgDown}
          />

          {/* existing zones */}
          {names.map((name) => {
            const poly = zones[name];
            const sel = name === selected;
            const cls = [
              'cc-ze-poly',
              sel ? 'selected' : '',
              danger ? 'danger' : '',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <polygon
                key={name}
                className={cls}
                points={poly.map((p) => p.join(',')).join(' ')}
                vectorEffect="non-scaling-stroke"
                pointerEvents={polyEvents ? 'all' : 'none'}
                style={{ cursor: danger ? 'pointer' : mode === 'view' ? 'pointer' : 'default' }}
                onClick={() => onPolyClick(name)}
              />
            );
          })}

          {/* zone labels — plain accent text anchored at the first vertex (matches LiveFeed) */}
          {names.map((name) => {
            const [lx, ly] = zones[name][0];
            return (
              <text
                key={`${name}-label`}
                className={`cc-ze-label-text${danger ? ' danger' : ''}`}
                x={lx + 6}
                y={ly - 8}
                fontSize={labelFont}
                pointerEvents="none"
              >
                ZONE · {name.toUpperCase()}
              </text>
            );
          })}

          {/* pending polygon */}
          {pending && pending.length > 0 && (
            <>
              <g pointerEvents="none">
                <polyline
                  className="cc-ze-pending-line"
                  points={pending.map((p) => p.join(',')).join(' ')}
                />
                <line
                  className="cc-ze-pending-cursor"
                  x1={pending[pending.length - 1][0]}
                  y1={pending[pending.length - 1][1]}
                  x2={cursor[0]}
                  y2={cursor[1]}
                />
              </g>
              {pending.map((p, i) => (
                <circle
                  key={i}
                  className="cc-ze-pending-dot"
                  cx={p[0]}
                  cy={p[1]}
                  r={vertexR}
                  vectorEffect="non-scaling-stroke"
                  pointerEvents="none"
                />
              ))}
            </>
          )}

          {/* vertex handles */}
          {names.map((name) => {
            if (!showHandlesFor(name)) return null;
            const sel = name === selected;
            return zones[name].map((p, idx) => {
              const cls = [
                'cc-ze-vertex',
                danger ? 'danger' : sel ? 'selected' : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <circle
                  key={`${name}-${idx}`}
                  className={cls}
                  cx={p[0]}
                  cy={p[1]}
                  r={vertexR}
                  vectorEffect="non-scaling-stroke"
                  pointerEvents="all"
                  onMouseDown={(e) => onVertexDown(name, idx, e)}
                  onContextMenu={(e) => e.preventDefault()}
                />
              );
            });
          })}
        </svg>

        {/* naming overlay */}
        {naming && (
          <div className="cc-ze-naming">
            <div className="cc-ze-naming-card">
              <div className="cc-ze-naming-label">
                NAME NEW ZONE · {pending?.length ?? 0} VERTICES
              </div>
              <input
                ref={inputRef}
                className="cc-ze-naming-input"
                value={nameInput}
                onChange={(e) => onNameInput(e.target.value)}
                onKeyDown={onNameKey}
                placeholder="e.g. front_door"
              />
              <div className="cc-ze-naming-actions">
                <button className="cc-ze-btn ghost" onClick={onCancelName}>
                  CANCEL
                </button>
                <button className="cc-ze-btn primary grow" onClick={onConfirmName}>
                  ADD ZONE
                </button>
              </div>
            </div>
          </div>
        )}

        {/* HUD */}
        <div className="cc-ze-hud-rec">
          <span className="dot" />
          <span className="label">REC</span>
          <span className="cam">CAM 01 — FRONT</span>
        </div>
        <div className="cc-ze-hud-frame">FRAME {meta ? meta.frame_id.toLocaleString('en-US') : '—'}</div>
        <div className="cc-ze-hud-cursor">
          X {pad4(cursor[0])}  Y {pad4(cursor[1])}
        </div>
      </div>
    </div>
  );
}
