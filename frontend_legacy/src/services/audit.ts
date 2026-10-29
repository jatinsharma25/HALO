import { fetchApi } from './api';

export interface AuditEntry {
  id: number;
  action: string;
  actor_id: number | null;
  target_type: string | null;
  target_id: number | null;
  timestamp: string;
  payload: string;
  entry_hash: string;
}

export interface ChainIntegrity {
  intact: boolean;
  first_tampered_id: number | null;
}

export const auditService = {
  getEntries: (limit = 100) => fetchApi<AuditEntry[]>(`/audit?limit=${limit}`),
  verifyChain: () => fetchApi<ChainIntegrity>('/audit/verify'),
};
