export type Role = "admin" | "operator" | "responder"

export interface CurrentUser {
  id: number
  username: string
  role: Role
}

export type CameraStatus = "active" | "offline" | "frozen" | "blackout" | "blurred" | "unknown"

export type TrackingState = "idle" | "tracking" | "target_lost" | "error"

export interface TrackingStatus {
  enabled: boolean
  state: TrackingState
  camera_id: number | null
  target_track_id: string | null
  pan: number
  tilt: number
}

export interface HardwareStatus {
  connected: boolean
  port: string
  baud_rate: number
  last_pan: number | null
  last_tilt: number | null
  error_count: number
  last_error: string | null
  available_ports: string[]
}

export interface Camera {
  id: number
  name: string
  source_uri: string
  status: CameraStatus
  created_at: string | null
}

export interface Zone {
  id: number
  camera_id: number
  name: string
  polygon_points: [number, number][]  // pixel coords on a 1280x720 frame
  zone_type: "restricted" | "monitored" | "safe"
  risk_level: number
  loitering_threshold_s: number | null  // null = use the global default
}

export interface Schedule {
  id: number
  camera_id: number
  name: string
  start_time: string  // "HH:MM"
  end_time: string    // "HH:MM"
  days_of_week: string[]  // ["Mon", "Tue", ...]
}

export interface SOP {
  id: number
  incident_type: string
  title: string
  steps_text: string
}

export interface Observation {
  id: number
  camera_id: number
  event_type: string
  timestamp: string
  confidence_score: number
  impact_score: number
  explanation: string
}

export interface IncidentExplanation {
  rule: string
  camera: string
  zone: string | null
  observation_count: number
  first_observed: string
  last_observed: string
  avg_detector_confidence: number
  camera_health_at_scoring: string
  access_event_matched: boolean
  narrative: string
}

export type IncidentDisposition = "true_positive" | "false_positive" | "uncertain"

export interface Incident {
  id: number
  type: string | null  // derived from explanation.rule; null until scored
  status: "new" | "acknowledged" | "investigating" | "escalated" | "resolved"
  created_at: string | null
  updated_at: string | null
  impact_score: number | null
  confidence_score: number | null
  explanation: IncidentExplanation | null
  assigned_to: number | null
  dedup_hash: string | null
  correlation_window_start: string | null
  correlation_window_end: string | null
  observation_count: number
  evidence_count: number
  disposition: IncidentDisposition | null
}

export interface IncidentDetail extends Incident {
  observations: Observation[]
  events: IncidentEvent[]
}

export interface IncidentEvent {
  id: number
  actor_id: number | null
  action: string
  ts: string
  note: string | null
}

export interface EvidencePackage {
  id: number
  incident_id: number
  clip_path: string
  has_original: boolean
  manifest_hash: string
  signature: string
  ed25519_signature: string | null
  created_at: string | null
}

export interface VerifyResult {
  evidence_id: number
  clip_present: boolean
  hash_matches: boolean
  ed25519_valid: boolean | null
  intact: boolean
}

export interface AuditLogEntry {
  id: number
  action: string
  actor_id: number | null
  target_type: string | null
  target_id: number | null
  timestamp: string
  payload: string | null
  entry_hash: string
}

export interface AuditVerifyResult {
  intact: boolean
  first_tampered_id: number | null
  total_entries: number
}

export interface ModelPassport {
  model_name: string
  model_version: string
  task: string
  training_data: string
  tracking: string
  known_limitations: string[]
  excluded_capabilities: string[]
}

export interface ScorecardRun {
  id: string
  run_at: string
  scenario_id: string
  precision: number
  recall: number
  avg_latency_ms: number
  model_version: string
  notes: string | null
}
