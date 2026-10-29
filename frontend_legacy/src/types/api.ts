export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  username: string;
}

export interface UserMeResponse {
  id: number;
  username: string;
  role: string;
}

export type CameraStatus = 'unknown' | 'active' | 'offline';

export interface Camera {
  id: number;
  name: string;
  source_uri: string;
  status: CameraStatus;
  created_at: string | null;
}

export interface Observation {
  id: number;
  camera_id: number;
  track_id: number;
  event_type: string;
  timestamp: string;
  zone_id: string | null;
  confidence_score: number;
  impact_score: number;
  explanation: string;
  raw_metadata?: string | null;
}

export interface CameraStatusResponse {
  camera_id: number;
  state: string;
  pipeline: boolean;
}

export interface CameraPipelineResponse {
  camera_id: number;
  status: string;
}
