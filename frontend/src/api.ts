// Types mirror the JSON returned by backend/main.py.

export type Lane = {
  id: number;
  origin: string;
  destination: string;
  tons: number;
  max_days: number;
  email: string;
  requirements: string[];
  route: string[];
  transit_days: number | null;
  met: string[];
  unmet: string[];
  issue: string | null;
  price: number | null;
};

export type Email = {
  id: number;
  direction: "in" | "out";
  party: string;
  subject: string;
  body: string;
  created_at: string;
};

export type AgentEvent = {
  id: number;
  agent: string;
  message: string;
  needs_human: number;
  created_at: string;
};

export type RfpSummary = { id: number; customer_email: string; status: string; created_at: string };

export type Rfp = RfpSummary & {
  quote: string | null;
  lanes: Lane[];
  emails: Email[];
  pricing_draft: string | null;
  missing_prices: string[];
  proposal: { lane_count: number; total_tons: number; total_value: number } | null;
  meeting: { title: string; starts_at: string; attendees: string[] } | null;
};

export const REQUIREMENTS = [
  "Temperature controlled (2-8 C)",
  "Dangerous goods",
  "High-value security",
  "Fragile handling",
  "Oversized cargo",
];

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : response.statusText);
  }
  return response.json();
}

export const api = {
  listRfps: () => call<RfpSummary[]>("GET", "/rfps"),
  getRfp: (id: number) => call<Rfp>("GET", `/rfps/${id}`),
  events: (id: number) => call<AgentEvent[]>("GET", `/rfps/${id}/events`),
  createSample: () => call<{ id: number }>("POST", "/rfps/sample"),
  upload: (file: File, customerEmail: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("customer_email", customerEmail);
    return call<{ id: number }>("POST", "/rfps", form);
  },
  setRequirements: (laneId: number, requirements: string[]) =>
    call("PUT", `/lanes/${laneId}/requirements`, { requirements }),
  setPrice: (laneId: number, price: number) => call("PUT", `/lanes/${laneId}/price`, { price }),
  approvePlan: (id: number) => call("POST", `/rfps/${id}/approve-plan`),
  approvePrices: (id: number) => call("POST", `/rfps/${id}/approve-prices`),
  approveQuote: (id: number, text: string) => call("POST", `/rfps/${id}/approve-quote`, { text }),
  customerReply: (id: number, text: string) => call("POST", `/rfps/${id}/customer-reply`, { text }),
  decide: (id: number, decision: "accepted" | "declined") => call("POST", `/rfps/${id}/decide`, { decision }),
};

// SQLite's CURRENT_TIMESTAMP is UTC without a "Z", so add it before parsing.
export const toDate = (sqliteTime: string) => new Date(sqliteTime.replace(" ", "T") + "Z");
