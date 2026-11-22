import { useState } from "react";
import { api, type Rfp } from "./api";

type Props = { rfp: Rfp; busy: boolean; run: (action: () => Promise<unknown>) => void };

const REPLY_EXAMPLES = {
  Accept: "Thanks, we accept the proposal. Please go ahead.",
  Decline: "Thank you, but we have decided to go with another carrier.",
  Unclear: "Looks good overall, but can you lower the price on the dangerous goods lanes?",
};

// The yellow box: tells the user what the agents need from them right now.
export function HumanAction({ rfp, busy, run }: Props) {
  const [quote, setQuote] = useState(rfp.quote ?? "");
  const [reply, setReply] = useState(REPLY_EXAMPLES.Accept);

  if (rfp.status === "working") return <div className="action agent">Agents are working…</div>;
  if (rfp.status === "lost") return <div className="action done">The customer declined. RFP closed.</div>;
  if (rfp.status === "won") {
    return (
      <div className="action done">
        <strong>The customer accepted.</strong> Kickoff meeting on{" "}
        {rfp.meeting && new Date(rfp.meeting.starts_at).toLocaleString()}. Proposal saved to the database:{" "}
        {rfp.proposal?.lane_count} lanes, {rfp.proposal?.total_tons.toFixed(1)} tons, $
        {rfp.proposal?.total_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}.
      </div>
    );
  }

  return (
    <div className="action human">
      <strong>Your action is needed</strong>

      {rfp.status === "review_plan" && (
        <>
          <p>
            Check the requirements read from each shipper email and the planned routes (click a lane to see its
            email and edit its requirements). Approving sends this email to the Pricing team:
          </p>
          <pre>{rfp.pricing_draft}</pre>
          <button className="primary" disabled={busy} onClick={() => run(() => api.approvePlan(rfp.id))}>
            Approve and send pricing request
          </button>
        </>
      )}

      {rfp.status === "review_prices" && (
        <>
          <p>Check the prices the agent read from the Pricing team's reply (see the Mailbox). You can edit any price in the table.</p>
          {rfp.missing_prices.length > 0 && (
            <p className="error">Missing price: {rfp.missing_prices.join(", ")}. Enter it in the table first.</p>
          )}
          <button
            className="primary"
            disabled={busy || rfp.missing_prices.length > 0}
            onClick={() => run(() => api.approvePrices(rfp.id))}
          >
            Approve prices and draft the quote
          </button>
        </>
      )}

      {rfp.status === "review_quote" && (
        <>
          <p>Edit the quote if needed. Nothing is sent to {rfp.customer_email} until you approve.</p>
          <textarea rows={14} value={quote} onChange={(e) => setQuote(e.target.value)} />
          <button className="primary" disabled={busy || !quote.trim()} onClick={() => run(() => api.approveQuote(rfp.id, quote))}>
            Approve and send to customer
          </button>
        </>
      )}

      {rfp.status === "awaiting_customer" && (
        <>
          <p>Simulator: write the customer's reply. The Customer Agent reads it and decides what happens next.</p>
          {Object.entries(REPLY_EXAMPLES).map(([label, text]) => (
            <button key={label} onClick={() => setReply(text)}>
              {label}
            </button>
          ))}
          <textarea rows={3} value={reply} onChange={(e) => setReply(e.target.value)} />
          <button className="primary" disabled={busy || !reply.trim()} onClick={() => run(() => api.customerReply(rfp.id, reply))}>
            Send reply as customer
          </button>
        </>
      )}

      {rfp.status === "review_reply" && (
        <>
          <p>The agent could not tell whether the customer accepted. Read their reply in the Mailbox and decide.</p>
          <button className="primary" disabled={busy} onClick={() => run(() => api.decide(rfp.id, "accepted"))}>
            Customer accepted
          </button>
          <button disabled={busy} onClick={() => run(() => api.decide(rfp.id, "declined"))}>
            Customer declined
          </button>
        </>
      )}
    </div>
  );
}
