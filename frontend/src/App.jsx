import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchBoard, movePo, sendTestWebhook } from "./api";
import Board from "./Board.jsx";

const COLUMNS = [
  { id: "new", title: "New", hint: "Placed in Odoo" },
  { id: "in_review", title: "In review", hint: "Check vendor & package" },
  { id: "in_progress", title: "In progress", hint: "Assigned / mapping" },
  { id: "done", title: "Done", hint: "Processed" },
];

export default function App() {
  const [columns, setColumns] = useState({});
  const [projectFilter, setProjectFilter] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastSync, setLastSync] = useState(null);
  const [highlightId, setHighlightId] = useState(null);
  const [live, setLive] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchBoard(projectFilter || undefined);
      setColumns(data.columns || {});
      setError("");
      setLive(true);
      setLastSync(new Date());
    } catch (err) {
      setError(err.message);
      setLive(false);
    } finally {
      setLoading(false);
    }
  }, [projectFilter]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!highlightId) return undefined;
    const timer = setTimeout(() => setHighlightId(null), 8000);
    return () => clearTimeout(timer);
  }, [highlightId]);

  const projects = useMemo(() => {
    const names = new Set();
    Object.values(columns).forEach((cards) => {
      (cards || []).forEach((card) => {
        if (card.project_id) names.add(card.project_id);
      });
    });
    return [...names].sort();
  }, [columns]);

  async function onDrop(cardId, status) {
    try {
      await movePo(cardId, status);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function simulateWebhook() {
    const stamp = Date.now().toString().slice(-5);
    try {
      await sendTestWebhook({
        _id: Number(stamp),
        _model: "purchase.order",
        display_name: `PO/${stamp}`,
        package_id: [1, "PKG-SOLAR-01"],
        partner_id: [12, "Helios Supplies"],
        project_id: [4, "Rajasthan 50MW"],
        subject: "Inverters and combiner boxes",
        category: "Electrical",
      });
    } catch (err) {
      setError(err.message);
    }
  }

  const total = Object.values(columns).reduce((sum, list) => sum + (list?.length || 0), 0);

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <p className="eyebrow">Odoo integration</p>
          <h1>Purchase order kanban</h1>
          <p className="sub">
            Place a purchase order in Odoo. The webhook posts it here and the card appears in{" "}
            <strong>New</strong> with vendor, project, package, subject, and category.
          </p>
        </div>
        <div className="actions">
          <label>
            Project
            <select value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
              <option value="">All projects</option>
              {projects.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={load}>
            Refresh
          </button>
          <button type="button" className="primary" onClick={simulateWebhook}>
            Simulate Odoo PO
          </button>
        </div>
      </header>

      <section className="meta">
        <span>{total} purchase orders</span>
        <span className={live ? "live" : ""}>{live ? "Listening for Odoo POs" : "Connecting…"}</span>
        <span>{loading ? "Loading…" : lastSync ? `Synced ${lastSync.toLocaleTimeString()}` : ""}</span>
      </section>

      {error ? <div className="banner error">{error}</div> : null}
      {notice ? <div className="banner ok">{notice}</div> : null}

      <Board
        columns={COLUMNS}
        data={columns}
        onDrop={onDrop}
        highlightId={highlightId}
        emptyNew="Waiting for a purchase order from Odoo"
      />
    </div>
  );
}
