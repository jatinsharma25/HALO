import { api } from "./api"
import type { HardwareStatus, TrackingStatus } from "./types"

export const trackingApi = {
  getHardwareStatus: () => api.get<HardwareStatus>("/hardware/status"),

  connectHardware: (port: string, baud_rate: number = 115200) =>
    api.post<{ connected: boolean; port: string }>("/hardware/connect", { port, baud_rate }),

  disconnectHardware: () =>
    api.post<{ connected: boolean }>("/hardware/disconnect"),

  getTrackingStatus: (cameraId: number) =>
    api.get<TrackingStatus>(`/cameras/${cameraId}/tracking`),

  startTracking: (cameraId: number) =>
    api.post<{ enabled: boolean; camera_id: number; state: string }>(`/cameras/${cameraId}/tracking/start`),

  stopTracking: (cameraId: number) =>
    api.post<{ enabled: boolean; camera_id: number; state: string }>(`/cameras/${cameraId}/tracking/stop`),

  homeServos: (cameraId: number) =>
    api.post<{ pan: number; tilt: number }>(`/cameras/${cameraId}/tracking/home`),

  manualMove: (cameraId: number, pan: number, tilt: number) =>
    api.post<{ pan: number; tilt: number }>(`/cameras/${cameraId}/tracking/manual`, { pan, tilt }),
}
