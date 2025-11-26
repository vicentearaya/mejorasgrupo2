const API_LOG =
  import.meta.env.VITE_API_LOGISTICA ||
  '/api/logistica'; // ✅ Usar proxy Nginx para evitar CORS

export type DeliveryRequest = {
  id: number;
  origin?: Record<string, any> | null;
  destination?: Record<string, any> | null;
  vehicle_id?: string | null;
  status: string;
  eta?: number | null;
  payload?: Record<string, any> | null;
  created_at?: string | null;
};

export type IncidentCreate = {
  delivery_request_id: number;
  route_id?: number | null;
  route_stop_id?: number | null;
  vehicle_id?: number | null;
  driver_id?: number | null;
  // severity will be derived server-side from type if not specified
  severity?: string | null;
  type?: string | null;
  description?: string | null;
};

export type IncidentOut = Required<IncidentCreate> & { id: number; created_at?: string | null };

export async function getDeliveryRequests(): Promise<DeliveryRequest[]> {
  const res = await fetch(`${API_LOG}/maps/delivery_requests`);
  if (!res.ok) throw new Error('Error al cargar cargamentos');
  return res.json();
}

export async function postIncident(payload: IncidentCreate): Promise<IncidentOut> {
  const res = await fetch(`${API_LOG}/maps/incidents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    let detail = '';
    try { detail = await res.text(); } catch { }
    throw new Error('Error al registrar incidente: ' + detail);
  }
  return res.json();
}

export type IncidentsFilter = {
  delivery_request_id?: number;
  route_id?: number;
  route_stop_id?: number;
  vehicle_id?: number;
  driver_id?: number;
  severity?: 'low' | 'medium' | 'high';
  type?: string;
  created_from?: string; // ISO
  created_to?: string;   // ISO
  limit?: number;
  offset?: number;
  order?: 'asc' | 'desc';
};

export async function getIncidents(filter: IncidentsFilter = {}): Promise<IncidentOut[]> {
  const params = new URLSearchParams();
  Object.entries(filter).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    params.set(k, String(v));
  });
  const url = `${API_LOG}/maps/incidents${params.toString() ? `?${params.toString()}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Error al cargar incidentes');
  return res.json();
}
