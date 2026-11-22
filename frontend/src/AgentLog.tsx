import { useEffect, useState } from "react";
import { api, toDate, type AgentEvent } from "./api";

// Polls the event log so you can watch the agents while a step runs.
export function AgentLog({ rfpId }: { rfpId: number }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);

  useEffect(() => {
    const load = () => api.events(rfpId).then(setEvents).catch(() => {});
    load();
    const timer = setInterval(load, 1500);
    return () => clearInterval(timer);
  }, [rfpId]);

  return (
    <ol className="events">
      {events.map((event) => (
        <li key={event.id} className={event.needs_human ? "needs-human" : ""}>
          <small>
            {toDate(event.created_at).toLocaleTimeString()} · <strong>{event.agent}</strong>
          </small>
          <div>{event.message}</div>
        </li>
      ))}
    </ol>
  );
}
