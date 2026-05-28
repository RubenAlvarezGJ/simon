import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { api, zonesSchema } from '../lib/api';
import { findContainingZone, nearestVertex } from '../lib/polygon';
import type { Point, Polygon, SnapshotMeta, ZonesMap } from '../lib/types';

type Mode = 'view' | 'draw' | 'edit' | 'delete';
const VERTEX_HIT_RADIUS = 10;

interface DragState {
  zone: string;
  vertexIdx: number;
}

export function ZoneEditor() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [meta, setMeta] = useState<SnapshotMeta | null>(null);
  const [snapshotUrl, setSnapshotUrl] = useState<string>('');
  const [zones, setZones] = useState<ZonesMap>({});
  const [mode, setMode] = useState<Mode>('view');
  const [pending, setPending] = useState<Polygon | null>(null);
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [status, setStatus] = useState<string>('');
  const [bgImage, setBgImage] = useState<HTMLImageElement | null>(null);

  // Load initial snapshot + zones
  useEffect(() => {
    void refreshSnapshot();
    void api
      .getZones()
      .then(setZones)
      .catch((err) => setStatus(`Failed to load zones: ${err}`));
  }, []);

  async function refreshSnapshot() {
    try {
      const m = await api.getSnapshotMeta();
      setMeta(m);
      setSnapshotUrl(api.snapshotUrl(true));
    } catch (err) {
      setStatus(`Snapshot unavailable: ${err}`);
    }
  }

  // Load <img> for canvas drawing whenever snapshotUrl changes
  useEffect(() => {
    if (!snapshotUrl) return;
    const img = new Image();
    img.onload = () => setBgImage(img);
    img.src = snapshotUrl;
  }, [snapshotUrl]);

  // Re-draw on any change
  useEffect(() => {
    drawCanvas();
  });

  function drawCanvas() {
    const canvas = canvasRef.current;
    if (!canvas || !meta) return;
    canvas.width = meta.width;
    canvas.height = meta.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (bgImage) {
      ctx.drawImage(bgImage, 0, 0, canvas.width, canvas.height);
    } else {
      ctx.fillStyle = '#222';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    for (const [name, poly] of Object.entries(zones)) {
      drawPolygon(ctx, poly, name, 'rgba(64, 200, 255, 0.25)', 'rgba(64, 200, 255, 0.9)');
    }
    if (pending && pending.length > 0) {
      drawPolygon(ctx, pending, '(new)', 'rgba(255, 200, 0, 0.2)', 'rgba(255, 200, 0, 0.95)', true);
    }
  }

  function canvasPoint(e: MouseEvent<HTMLCanvasElement>): Point {
    const canvas = canvasRef.current;
    if (!canvas) return [0, 0];
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / rect.width;
    const sy = canvas.height / rect.height;
    const clamp = (v: number, max: number) => Math.min(max, Math.max(0, v));
    return [
      clamp(Math.round((e.clientX - rect.left) * sx), canvas.width),
      clamp(Math.round((e.clientY - rect.top) * sy), canvas.height),
    ];
  }

  function onMouseDown(e: MouseEvent<HTMLCanvasElement>) {
    if (!meta) return;
    const p = canvasPoint(e);
    if (mode === 'draw') {
      if (e.button !== 0) return;
      setPending((cur) => [...(cur ?? []), p]);
      return;
    }
    if (mode === 'edit') {
      for (const [name, poly] of Object.entries(zones)) {
        const idx = nearestVertex(poly, p, VERTEX_HIT_RADIUS);
        if (idx !== -1) {
          if (e.button === 2 && poly.length > 3) {
            // Right-click to delete vertex.
            e.preventDefault();
            const next = poly.filter((_, i) => i !== idx);
            setZones({ ...zones, [name]: next });
          } else {
            setDragging({ zone: name, vertexIdx: idx });
          }
          return;
        }
      }
      return;
    }
    if (mode === 'delete') {
      const containing = findContainingZone(zones, p);
      if (containing) {
        const next = { ...zones };
        delete next[containing];
        setZones(next);
        setStatus(`Deleted zone "${containing}". Click Save to persist.`);
      }
    }
  }

  function onMouseMove(e: MouseEvent<HTMLCanvasElement>) {
    if (!dragging) return;
    const p = canvasPoint(e);
    setZones((cur) => {
      const poly = cur[dragging.zone];
      if (!poly) return cur;
      const next = poly.slice();
      next[dragging.vertexIdx] = p;
      return { ...cur, [dragging.zone]: next };
    });
  }

  function onMouseUp() {
    setDragging(null);
  }

  function onDoubleClick() {
    if (mode !== 'draw') return;
    if (!pending || pending.length < 3) {
      setStatus('Need at least 3 vertices.');
      return;
    }
    const name = window.prompt('Zone name?')?.trim();
    if (!name) {
      setStatus('Cancelled.');
      setPending(null);
      return;
    }
    setZones({ ...zones, [name]: pending });
    setPending(null);
    setStatus(`Added zone "${name}". Click Save to persist.`);
  }

  async function save() {
    try {
      zonesSchema.parse(zones);
      await api.putZones(zones);
      setStatus(`Saved ${Object.keys(zones).length} zone(s).`);
    } catch (err) {
      setStatus(`Save failed: ${err}`);
    }
  }

  return (
    <div className="panel zone-editor">
      <div className="editor-toolbar">
        <h3>Zone editor</h3>
        <select value={mode} onChange={(e) => { setMode(e.target.value as Mode); setPending(null); }}>
          <option value="view">View</option>
          <option value="draw">Draw new</option>
          <option value="edit">Edit vertices</option>
          <option value="delete">Delete</option>
        </select>
        <button onClick={() => void refreshSnapshot()}>Refresh snapshot</button>
        <button onClick={() => void save()}>Save</button>
        <span className="muted">{status}</span>
      </div>
      <div className="canvas-wrap">
        {meta ? (
          <canvas
            ref={canvasRef}
            onContextMenu={(e) => e.preventDefault()}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onDoubleClick={onDoubleClick}
          />
        ) : (
          <div className="muted">Waiting for first frame…</div>
        )}
      </div>
      <ZoneListing zones={zones} />
    </div>
  );
}

function ZoneListing({ zones }: { zones: ZonesMap }) {
  const names = Object.keys(zones);
  if (names.length === 0) return <div className="muted">No zones defined.</div>;
  return (
    <ul className="zone-list">
      {names.map((n) => (
        <li key={n}>
          <strong>{n}</strong> <span className="muted">({zones[n].length} pts)</span>
        </li>
      ))}
    </ul>
  );
}

function drawPolygon(
  ctx: CanvasRenderingContext2D,
  poly: Polygon,
  label: string,
  fill: string,
  stroke: string,
  showHandles: boolean = true,
) {
  if (poly.length === 0) return;
  ctx.beginPath();
  ctx.moveTo(poly[0][0], poly[0][1]);
  for (let i = 1; i < poly.length; i++) {
    ctx.lineTo(poly[i][0], poly[i][1]);
  }
  if (poly.length >= 3) ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  ctx.stroke();

  if (showHandles) {
    ctx.fillStyle = stroke;
    for (const [x, y] of poly) {
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (poly.length > 0) {
    const [lx, ly] = poly[0];
    ctx.fillStyle = '#fff';
    ctx.font = '13px system-ui, sans-serif';
    ctx.fillText(label, lx + 6, ly - 6);
  }
}
