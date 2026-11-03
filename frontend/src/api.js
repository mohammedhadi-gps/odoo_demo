const API = (import.meta.env.VITE_API_BASE_URL || "") + "/api/v1";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || "Request failed");
  }
  return response.json();
}

export function fetchBoard(projectId) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return request(`/po/board${query}`);
}

export function movePo(id, status) {
  return request(`/po/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function sendTestWebhook(payload) {
  return request("/odoo/po-webhook", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function subscribeBoard(onEvent) {
  const source = new EventSource(`${API}/po/events`);
  source.onmessage = (event) => {
    try {
      onEvent(JSON.parse(event.data));
    } catch {
      onEvent({ type: "refresh" });
    }
  };
  source.onerror = () => {};
  return () => source.close();
}

/** Trigger a manual Odoo JSON-RPC sync for one PO by its local DB id. */
export function syncPo(id) {
  return request(`/po/${id}/sync`, { method: "POST" });
}

/** Pull the latest 3 confirmed POs from Odoo into the kanban. */
export function pullFromOdoo(limit = 3) {
  return request(`/odoo/pull?limit=${limit}`, { method: "POST" });
}

/** Delete a PO from the kanban board by its local DB id. */
export async function deletePo(id) {
  const response = await fetch(`${API}/po/${id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || "Delete failed");
  }
}
