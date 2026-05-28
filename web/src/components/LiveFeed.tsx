import { useEffect, useRef, useState } from 'react';
import { useEventStreamContext } from '../context/EventStreamContext';

export function LiveFeed() {
  const { connected, last_frame_id } = useEventStreamContext();
  const [stalled, setStalled] = useState(false);
  const lastSeenRef = useRef<number>(0);
  const lastChangeRef = useRef<number>(Date.now());

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

  return (
    <div className="live-feed">
      <div className="feed-header">
        <span className={connected ? 'pill ok' : 'pill bad'}>
          {connected ? 'WS connected' : 'WS offline'}
        </span>
        <span className="pill">frame #{last_frame_id}</span>
        {stalled && <span className="pill warn">no new frames</span>}
      </div>
      <img
        src="/api/stream.mjpg"
        alt="Live annotated feed"
        className="feed-img"
      />
    </div>
  );
}
