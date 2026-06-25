import { useEffect, useRef, useState } from 'react';
import { useEventStreamContext } from '../context/EventStreamContext';
import { formatClock, formatDate, num } from '../lib/format';

interface Props {
  fps: number;
  now: Date;
}

const CAM_LABEL = 'CAM 01 — FRONT';

export function LiveFeed({ fps, now }: Props) {
  const { connected, last_frame_id, hello } = useEventStreamContext();
  const [stalled, setStalled] = useState(false);
  const [imgError, setImgError] = useState(false);
  const lastSeenRef = useRef<number>(0);
  const lastChangeRef = useRef<number>(0);

  useEffect(() => {
    if (last_frame_id !== lastSeenRef.current) {
      lastSeenRef.current = last_frame_id;
      lastChangeRef.current = Date.now();
      setStalled(false);
    }
  }, [last_frame_id]);

  useEffect(() => {
    const id = setInterval(() => {
      const idle = Date.now() - lastChangeRef.current;
      setStalled(idle > 4000 && last_frame_id > 0);
    }, 1000);
    return () => clearInterval(id);
  }, [last_frame_id]);

  // numpy frame.shape is (height, width); zones are pixel [x, y].
  const frameShape = hello?.frame_shape ?? null;
  const fh = frameShape ? frameShape[0] : 0;
  const fw = frameShape ? frameShape[1] : 0;
  const zones = hello?.zones ?? {};
  const hasFeed = !imgError && last_frame_id > 0;

  const recColor = connected ? (stalled ? 'var(--warn)' : 'var(--bad-bright)') : 'var(--muted)';
  const recLabel = connected ? (stalled ? 'STALLED' : 'REC') : 'OFFLINE';

  return (
    <div className="cc-feed">
      {!hasFeed && (
        <div className="cc-feed-empty">
          <div className="l1">[ LIVE FEED ]</div>
          <div className="l2">ANNOTATED MJPEG · /api/stream.mjpg</div>
        </div>
      )}

      <img
        className="cc-feed-img"
        src="/api/stream.mjpg"
        alt="Live annotated feed"
        style={{ opacity: hasFeed ? 1 : 0 }}
        onError={() => setImgError(true)}
        onLoad={() => setImgError(false)}
      />

      {/* Real zone polygons, aligned to the contained image via meet. */}
      {fw > 0 && fh > 0 && Object.keys(zones).length > 0 && (
        <svg
          className="cc-feed-svg"
          viewBox={`0 0 ${fw} ${fh}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {Object.entries(zones).map(([name, poly]) => {
            if (!poly || poly.length < 3) return null;
            const points = poly.map(([x, y]) => `${x},${y}`).join(' ');
            const [lx, ly] = poly[0];
            return (
              <g key={name}>
                <polygon
                  points={points}
                  fill="rgba(47,214,255,.05)"
                  stroke="var(--ac)"
                  strokeWidth={1.1}
                  strokeDasharray="6 6"
                  vectorEffect="non-scaling-stroke"
                  opacity={0.65}
                />
                <text
                  x={lx + 6}
                  y={ly - 8}
                  fill="var(--ac)"
                  fontSize={Math.max(12, Math.round(fh / 48))}
                  letterSpacing="1"
                >
                  ZONE · {name.toUpperCase()}
                </text>
              </g>
            );
          })}
        </svg>
      )}

      {/* corner brackets */}
      <div className="cc-bracket tl" />
      <div className="cc-bracket tr" />
      <div className="cc-bracket bl" />
      <div className="cc-bracket br" />

      {/* HUD overlays */}
      <div className="cc-hud-rec">
        <span className="dot" style={{ background: recColor, animation: 'pulseDot 1.2s infinite' }} />
        <span className="label" style={{ color: recColor }}>{recLabel}</span>
        <span className="cam">{CAM_LABEL}</span>
      </div>
      <div className="cc-hud-res">
        <span>{fw > 0 ? `${fw}×${fh}` : '—'}</span>
        <span className="fps">{fps} FPS</span>
      </div>
      <div className="cc-hud-ts">{formatDate(now)} {formatClock(now)}</div>
      <div className="cc-hud-frame">FRAME {num(last_frame_id)}</div>
    </div>
  );
}
