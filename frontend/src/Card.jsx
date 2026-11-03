import { useState } from "react";
import { syncPo } from "./api";

function fmt(val) {
  return val || "—";
}

function LineItemsTable({ items }) {
  if (!items || items.length === 0) {
    return <p className="lines-empty">No line items synced yet.</p>;
  }
  return (
    <div className="lines-wrap">
      <table className="lines-table">
        <thead>
          <tr>
            <th>Product</th>
            <th>Ordered</th>
            <th>Received</th>
            <th>Invoiced</th>
            <th>Unit Price</th>
          </tr>
        </thead>
        <tbody>
          {items.map((line) => (
            <tr key={line.id}>
              <td>{fmt(line.product_name)}</td>
              <td className="num">{line.qty_ordered ?? "—"}</td>
              <td className="num">{line.qty_received ?? "—"}</td>
              <td className="num">{line.qty_invoiced ?? "—"}</td>
              <td className="num">{line.price_unit != null ? line.price_unit.toFixed(2) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Card({ card, highlight, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState("");

  const isSynced = Boolean(card.odoo_synced_at);

  async function handleSync(e) {
    e.stopPropagation();
    setSyncing(true);
    setSyncError("");
    try {
      await syncPo(card.id);
      if (onRefresh) onRefresh();
    } catch (err) {
      setSyncError(err.message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <article
      className={`card ${highlight ? "highlight" : ""}`}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", String(card.id));
        event.dataTransfer.effectAllowed = "move";
      }}
    >
      {/* ── Header ── */}
      <div className="card-top">
        <strong>{card.display_name}</strong>
        {card.category ? <span className="tag">{card.category}</span> : null}
      </div>

      {card.subject ? <p className="subject">{card.subject}</p> : null}

      {/* ── Core fields ── */}
      <dl>
        <div><dt>Vendor</dt><dd>{fmt(card.partner_id)}</dd></div>
        <div><dt>Project</dt><dd>{fmt(card.project_id)}</dd></div>
        <div><dt>Package</dt><dd>{fmt(card.package_id)}</dd></div>
      </dl>

      {/* ── Enriched fields (shown once synced) ── */}
      {isSynced && (
        <dl className="enriched">
          {card.vendor_name && <div><dt>Vendor ref</dt><dd>{card.vendor_name}</dd></div>}
          {card.po_number   && <div><dt>PO number</dt><dd>{card.po_number}</dd></div>}
          {card.placement_date && <div><dt>Placed</dt><dd>{card.placement_date}</dd></div>}
          {card.confirmation_date && <div><dt>Confirmed</dt><dd>{card.confirmation_date}</dd></div>}
          {card.delivery_date && <div><dt>Delivery</dt><dd>{card.delivery_date}</dd></div>}
        </dl>
      )}

      {/* ── Line items toggle ── */}
      {isSynced && (
        <button
          type="button"
          className="lines-toggle"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "▲ Hide" : "▼ Line items"}
          {card.line_items?.length ? ` (${card.line_items.length})` : ""}
        </button>
      )}
      {expanded && <LineItemsTable items={card.line_items} />}

      {/* ── Sync button ── */}
      {card.odoo_id && (
        <div className="card-footer">
          <button
            type="button"
            className="sync-btn"
            onClick={handleSync}
            disabled={syncing}
          >
            {syncing ? "Syncing…" : isSynced ? "Re-sync Odoo" : "Sync from Odoo"}
          </button>
          {isSynced && (
            <span className="sync-ts">
              {new Date(card.odoo_synced_at).toLocaleTimeString()}
            </span>
          )}
          {syncError && <span className="sync-error">{syncError}</span>}
        </div>
      )}
    </article>
  );
}
