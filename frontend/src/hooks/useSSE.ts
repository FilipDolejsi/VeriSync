import { useEffect, useRef, useState } from 'react';
import { sseUrl, VSEvent } from '../lib/api';

export interface FeedEvent extends VSEvent {
  ts: string; // local timestamp
}

export function useSSE(enabled: boolean) {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [live, setLive]     = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const es = new EventSource(sseUrl(), { withCredentials: true });
    esRef.current = es;

    es.onopen    = () => setLive(true);
    es.onerror   = () => setLive(false);
    es.onmessage = (e) => {
      try {
        const ev: VSEvent = JSON.parse(e.data);
        setEvents(prev => [
          { ...ev, ts: new Date().toLocaleTimeString('en-GB', { hour12: false }) },
          ...prev.slice(0, 199),
        ]);
      } catch (_) {}
    };

    return () => { es.close(); setLive(false); };
  }, [enabled]);

  return { events, live };
}
