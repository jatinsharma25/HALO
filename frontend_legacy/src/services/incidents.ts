import { fetchApi } from './api';

export interface Incident {
  id: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  assigned_to: number | null;
  observation_count: number;
  evidence_count: number;
  correlation_window_start: string | null;
  correlation_window_end: string | null;
}

export interface EvidencePackage {
  id: number;
  incident_id: number;
  clip_path: string;
  manifest_hash: string;
  signature: string;
  ed25519_signature: string | null;
  created_at: string | null;
}

export interface EvidenceVerification {
  evidence_id: number;
  clip_present: boolean;
  hash_matches: boolean;
  /** null when the package predates Ed25519 signing. */
  ed25519_valid: boolean | null;
  intact: boolean;
}

export const INCIDENT_STATUSES = [
  'new',
  'acknowledged',
  'investigating',
  'escalated',
  'resolved',
] as const;

export const incidentsService = {
  getIncidents: (status?: string) =>
    fetchApi<Incident[]>(`/incidents${status ? `?status=${encodeURIComponent(status)}` : ''}`),

  getIncident: (id: number) => fetchApi<Incident>(`/incidents/${id}`),

  updateStatus: (id: number, newStatus: string, note?: string) =>
    fetchApi<Incident>(`/incidents/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ new_status: newStatus, note }),
    }),

  assign: (id: number, userId: number) =>
    fetchApi<Incident>(`/incidents/${id}/assign`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    }),

  getEvidence: (id: number) => fetchApi<EvidencePackage[]>(`/incidents/${id}/evidence`),

  packageEvidence: (id: number, paddingSeconds = 5) =>
    fetchApi<EvidencePackage>(`/incidents/${id}/evidence?padding_seconds=${paddingSeconds}`, {
      method: 'POST',
    }),

  verifyEvidence: (evidenceId: number) =>
    fetchApi<EvidenceVerification>(`/evidence/${evidenceId}/verify`),

  publicKey: () =>
    fetchApi<{ algorithm: string; public_key_pem: string }>('/evidence/public-key'),
};
