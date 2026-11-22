import { useEffect, useState } from "react";
import { api, toDate, type Rfp } from "./api";
import { HumanAction } from "./HumanAction";
import { LaneTable } from "./LaneTable";

export const STATUS_LABELS: Record<string, string> = {
  working: "Agents working",
  review_plan: "Needs human: review plan",
  review_prices: "Needs human: review prices",
  review_quote: "Needs human: approve quote",
  awaiting_customer: "Waiting for customer",
  review_reply: "Needs human: unclear reply",
  won: "Won",
  lost: "Lost",
};

export function RfpPage({ rfpId, onChange }: { rfpId: number; onChange: () => void }) {
  const [rfp, setRfp] = useState<Rfp | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => api.getRfp(rfpId).then(setRfp).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, [rfpId]);

  // Runs any API action, then reloads the RFP so the page shows the new status.
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      await load();
      onChange();
      setBusy(false);
    }
  }

  if (!rfp) return <p>{error || "Loading…"}</p>;

  return (
    <div className="rfp-page">
      <header>
        <h2>
          RFP #{rfp.id} · {rfp.customer_email}
        </h2>
        <span className={`status status-${rfp.status}`}>{STATUS_LABELS[rfp.status] ?? rfp.status}</span>
      </header>

      {/* key={status} resets the box's text fields whenever the workflow moves to a new step */}
      <HumanAction key={rfp.status} rfp={rfp} busy={busy} run={run} />
      {error && <p className="error">{error}</p>}

      <h3>Lanes</h3>
      <LaneTable rfp={rfp} run={run} />

      <h3>Mailbox</h3>
      {rfp.emails.length === 0 && <p className="muted">No emails yet.</p>}
      {rfp.emails.map((email) => (
        <details key={email.id} className="email">
          <summary>
            {email.direction === "out" ? "Sent to" : "Received from"} {email.party}: <strong>{email.subject}</strong>{" "}
            <small>{toDate(email.created_at).toLocaleString()}</small>
          </summary>
          <pre>{email.body}</pre>
        </details>
      ))}
    </div>
  );
}
