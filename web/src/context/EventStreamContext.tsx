import { createContext, useContext, type ReactNode } from 'react';
import { useEventStream, type EventStreamState } from '../hooks/useEventStream';

const EventStreamContext = createContext<EventStreamState | null>(null);

export function EventStreamProvider({ children }: { children: ReactNode }) {
  const stream = useEventStream();
  return (
    <EventStreamContext.Provider value={stream}>
      {children}
    </EventStreamContext.Provider>
  );
}

export function useEventStreamContext(): EventStreamState {
  const ctx = useContext(EventStreamContext);
  if (ctx === null) {
    throw new Error('useEventStreamContext must be used inside EventStreamProvider');
  }
  return ctx;
}
