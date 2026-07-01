import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { api, zonesSchema } from '../lib/api';
import type { Point, Polygon, SnapshotMeta, ZonesMap } from '../lib/types';
import { ZoneToolbar } from './zone-editor/ZoneToolbar';
import { ZoneCanvas } from './zone-editor/ZoneCanvas';
import { ZoneList } from './zone-editor/ZoneList';
import { ZoneGuide } from './zone-editor/ZoneGuide';
import type { DragState, EditorStatus, Mode } from './zone-editor/types';

const STATUS_DOT: Record<EditorStatus['kind'], string> = {
  ok: 'var(--ok)',
  pending: 'var(--warn)',
  err: 'var(--bad)',
};

export function ZoneEditor() {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [meta, setMeta] = useState<SnapshotMeta | null>(null);
  const [snapshotUrl, setSnapshotUrl] = useState<string>('');
  const [zones, setZones] = useState<ZonesMap>({});
  const [mode, setMode] = useState<Mode>('view');
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState<Polygon | null>(null);
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [cursor, setCursor] = useState<Point>([960, 540]);
  const [naming, setNaming] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState<EditorStatus>({
    text: 'Loading zones from /api/zones…',
    kind: 'pending',
  });

  // Initial load: snapshot meta/url + zones.
  useEffect(() => {
    void refreshSnapshot();
    void api
      .getZones()
      .then((z) => {
        setZones(z);
        const n = Object.keys(z).length;
        setStatus({ text: `Loaded ${n} zone${n === 1 ? '' : 's'} from /api/zones.`, kind: 'ok' });
      })
      .catch((err) => setStatus({ text: `Failed to load zones: ${err}`, kind: 'err' }));
  }, []);

  // Focus the name input when the naming overlay opens.
  useEffect(() => {
    if (naming) inputRef.current?.focus();
  }, [naming]);

  async function refreshSnapshot() {
    try {
      const m = await api.getSnapshotMeta();
      setMeta(m);
      setSnapshotUrl(api.snapshotUrl(true));
    } catch (err) {
      setStatus({ text: `Snapshot unavailable: ${err}`, kind: 'err' });
    }
  }

  // Map a client-space event to image (viewBox) coordinates, clamped to frame bounds.
  function toImg(e: { clientX: number; clientY: number }): Point {
    const svg = svgRef.current;
    const w = meta?.width ?? 1920;
    const h = meta?.height ?? 1080;
    if (!svg) return [0, 0];
    const r = svg.getBoundingClientRect();
    const sx = w / r.width;
    const sy = h / r.height;
    const clamp = (v: number, m: number) => Math.min(m, Math.max(0, v));
    return [
      clamp(Math.round((e.clientX - r.left) * sx), w),
      clamp(Math.round((e.clientY - r.top) * sy), h),
    ];
  }

  function changeMode(m: Mode) {
    setMode(m);
    setPending(null);
    setNaming(false);
  }

  function onBgDown(e: MouseEvent) {
    if (e.button !== 0) return;
    if (mode === 'draw') {
      const p = toImg(e);
      setPending((cur) => {
        const next = [...(cur ?? []), p];
        setStatus({ text: `Vertex ${next.length} placed. Double-click to finish.`, kind: 'pending' });
        return next;
      });
      return;
    }
    // Non-draw modes: a background click is empty space → drop the current selection.
    if (selected !== null) setSelected(null);
  }

  function onMove(e: MouseEvent) {
    const p = toImg(e);
    if (dragging) {
      setZones((cur) => {
        const poly = cur[dragging.zone];
        if (!poly) return cur;
        const next = poly.slice();
        next[dragging.vertexIdx] = p;
        return { ...cur, [dragging.zone]: next };
      });
      setDirty(true);
    }
    setCursor(p);
  }

  function onUp() {
    if (dragging) setDragging(null);
  }

  function onDbl() {
    if (mode !== 'draw') return;
    if (!pending || pending.length < 3) {
      setStatus({ text: 'Need at least 3 vertices.', kind: 'err' });
      return;
    }
    setNaming(true);
    setNameInput('');
  }

  function onVertexDown(name: string, idx: number, e: MouseEvent) {
    e.stopPropagation();
    if (mode !== 'edit') return;
    if (e.button === 2) {
      e.preventDefault();
      setZones((cur) => {
        const poly = cur[name];
        if (!poly || poly.length <= 3) {
          setStatus({ text: 'A zone needs at least 3 vertices.', kind: 'err' });
          return cur;
        }
        setDirty(true);
        setStatus({ text: `Removed vertex from "${name}".`, kind: 'ok' });
        return { ...cur, [name]: poly.filter((_, i) => i !== idx) };
      });
      return;
    }
    setDragging({ zone: name, vertexIdx: idx });
    setSelected(name);
  }

  function onPolyClick(name: string) {
    if (mode === 'delete') {
      deleteZone(name);
    } else if (mode === 'view' || mode === 'edit') {
      setSelected(name);
    }
  }

  function deleteZone(name: string) {
    setZones((cur) => {
      const next = { ...cur };
      delete next[name];
      return next;
    });
    setSelected((cur) => (cur === name ? null : cur));
    setDirty(true);
    setStatus({ text: `Deleted zone "${name}". Save to persist.`, kind: 'err' });
  }

  function onDeleteFromList(name: string, e: MouseEvent) {
    e.stopPropagation();
    deleteZone(name);
  }

  function confirmName() {
    const raw = nameInput.trim();
    if (!raw) {
      setStatus({ text: 'Zone name required.', kind: 'err' });
      return;
    }
    if (!pending || pending.length < 3) {
      setStatus({ text: 'Need at least 3 vertices.', kind: 'err' });
      return;
    }
    const name = raw.replace(/\s+/g, '_').toLowerCase();
    setZones((cur) => ({ ...cur, [name]: pending }));
    setPending(null);
    setNaming(false);
    setSelected(name);
    setDirty(true);
    setStatus({ text: `Added zone "${name}". Save to persist.`, kind: 'ok' });
  }

  function cancelName() {
    setNaming(false);
    setStatus({ text: 'Cancelled. Pending shape kept — double-click to retry.', kind: 'pending' });
  }

  function onNameKey(e: KeyboardEvent) {
    if (e.key === 'Enter') confirmName();
    if (e.key === 'Escape') cancelName();
  }

  async function save() {
    try {
      zonesSchema.parse(zones);
      const res = await api.putZones(zones);
      setDirty(false);
      setStatus({ text: `Saved ${res.zones} zone(s) → PUT /api/zones · 200 OK.`, kind: 'ok' });
    } catch (err) {
      setStatus({ text: `Save failed: ${err}`, kind: 'err' });
    }
  }

  function refresh() {
    void refreshSnapshot();
    setStatus({ text: 'Fetched fresh snapshot.', kind: 'ok' });
  }

  return (
    <main className="cc-ze-main">
      <div className="cc-ze-col-right">
        <ZoneList
          zones={zones}
          selected={selected}
          mode={mode}
          onSelect={setSelected}
          onDelete={onDeleteFromList}
        />
        <ZoneGuide mode={mode} />
      </div>

      <div className="cc-ze-col-left">
        <ZoneToolbar mode={mode} onMode={changeMode} onRefresh={refresh} onSave={() => void save()} />

        <ZoneCanvas
          svgRef={svgRef}
          inputRef={inputRef}
          meta={meta}
          snapshotUrl={snapshotUrl}
          zones={zones}
          mode={mode}
          selected={selected}
          pending={pending}
          cursor={cursor}
          naming={naming}
          nameInput={nameInput}
          onBgDown={onBgDown}
          onMove={onMove}
          onUp={onUp}
          onDbl={onDbl}
          onPolyClick={onPolyClick}
          onVertexDown={onVertexDown}
          onNameInput={setNameInput}
          onNameKey={onNameKey}
          onConfirmName={confirmName}
          onCancelName={cancelName}
        />

        <div className="cc-ze-status">
          <span className="cc-ze-status-dot" style={{ background: STATUS_DOT[status.kind] }} />
          <span className="cc-ze-status-text">{status.text}</span>
          <span className="cc-ze-status-dirty">{dirty ? 'UNSAVED CHANGES' : 'ALL SAVED'}</span>
        </div>
      </div>
    </main>
  );
}
