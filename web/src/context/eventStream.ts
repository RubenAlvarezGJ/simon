import { createContext, useContext } from 'react';
import type { EventStream } from '../hooks/useEventStream';

// The context object and its consumer hook live apart from the provider
// component: a module that exports both a component and non-component values
// breaks Fast Refresh for everything that imports it.
export const EventStreamContext = createContext<EventStream | null>(null);

export function useEventStreamContext(): EventStream {
  const ctx = useContext(EventStreamContext);
  if (ctx === null) {
    throw new Error('useEventStreamContext must be used inside EventStreamProvider');
  }
  return ctx;
}
