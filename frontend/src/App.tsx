import { useEffect, useState } from "react";
import { AgentLog } from "./AgentLog";
import { api, type RfpSummary } from "./api";
import { RfpPage, STATUS_LABELS } from "./RfpPage";

export function App() {
  const [rfps, setRfps] = useState<RfpSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [customerEmail, setCustomerEmail] = useState("");

  const loadList = () => api.listRfps().then(setRfps).catch((e) => setError(e.message));
  useEffect(() => {
    loadList();
  }, []);

  async function create(request: () => Promise<{ id: number }>) {
    setBusy(true);
    setError("");
    try {
      const { id } = await request();
      await loadList();
      setSelectedId(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>RFP Copilot</h1>
        <button className="primary" disabled={busy} onClick={() => create(api.createSample)}>
          {busy ? "Agents working…" : "Load sample RFP"}
        </button>
        <details>
          <summary>Upload an RFP (.xlsx)</summary>
          <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input placeholder="Customer email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} />
          <button disabled={busy || !file || !customerEmail} onClick={() => create(() => api.upload(file!, customerEmail))}>
            Upload
          </button>
        </details>
        {error && <p className="error">{error}</p>}
        <ul className="rfp-list">
          {rfps.map((rfp) => (
            <li key={rfp.id}>
              <button className={rfp.id === selectedId ? "selected" : ""} onClick={() => setSelectedId(rfp.id)}>
                RFP #{rfp.id} · {rfp.customer_email}
                <small>{STATUS_LABELS[rfp.status] ?? rfp.status}</small>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main>{selectedId ? <RfpPage key={selectedId} rfpId={selectedId} onChange={loadList} /> : <p>Load or upload an RFP to start.</p>}</main>

      <aside className="agent-panel">
        <h2>Agent orchestration</h2>
        {selectedId ? <AgentLog key={selectedId} rfpId={selectedId} /> : <p className="muted">No RFP selected.</p>}
      </aside>
    </div>
  );
}
