const BASE = '/api/v1';

async function request(url, options = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

/** GET /api/v1/schedule?warehouseId=... → ScheduleResponse */
export const getSchedule = (warehouseId) =>
  request(`/schedule?warehouseId=${encodeURIComponent(warehouseId)}`);

/** GET /api/v1/dispatch/:id → DispatchDto */
export const getDispatch = (id) => request(`/dispatch/${id}`);

/** PATCH /api/v1/dispatch/:id/status → DispatchDto */
export const updateDispatchStatus = (id, newStatus) =>
  request(`/dispatch/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ newStatus }),
  });

/** POST /api/v1/ingest-data → { status, dispatches_created } */
export const ingestData = (payload) =>
  request('/ingest-data', { method: 'POST', body: JSON.stringify(payload) });

/**
 * Fetch schedule data for ALL warehouses in parallel.
 * Returns { [warehouseId]: { dispatches, tacticalPlan, generatedAt } }
 */
export const WAREHOUSE_IDS = ['1', '2', '3', '4', '5'];

export async function getAllSchedules() {
  const results = await Promise.allSettled(
    WAREHOUSE_IDS.map(id => getSchedule(id).then(data => ({ id, data })))
  );
  const map = {};
  for (const r of results) {
    if (r.status === 'fulfilled') {
      map[r.value.id] = r.value.data;
    }
  }
  return map;
}
