import { fetchApi } from './api';

export interface Alert {
  id: number;
  camera_id: number;
  camera_name: string;
  track_id: string;
  event_type: string;
  timestamp: string;
  zone_id: number | null;
  confidence_score: number;
  impact_score: number;
  explanation: string;
  raw_metadata: string | null;
  acknowledged: boolean;
  acknowledged_by: number | null;
  acknowledged_by_username: string | null;
  acknowledged_at: string | null;
}

export const alertsService = {
  getAlerts: (opts: { acknowledged?: boolean; cameraId?: number; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.acknowledged !== undefined) q.set('acknowledged', String(opts.acknowledged));
    if (opts.cameraId !== undefined) q.set('camera_id', String(opts.cameraId));
    q.set('limit', String(opts.limit ?? 100));
    return fetchApi<Alert[]>(`/alerts?${q.toString()}`);
  },

  acknowledge: (alertId: number) =>
    fetchApi<{ id: number; acknowledged: boolean }>(`/alerts/${alertId}/acknowledge`, {
      method: 'POST',
    }),
};
