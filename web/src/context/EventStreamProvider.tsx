import { type ReactNode } from 'react';
import { useEventStream } from '../hooks/useEventStream';
import { EventStreamContext } from './eventStream';

export function EventStreamProvider({ children }: { children: ReactNode }) {
  const stream = useEventStream();
  return (
    <EventStreamContext.Provider value={stream}>
      {children}
    </EventStreamContext.Provider>
  );
}
