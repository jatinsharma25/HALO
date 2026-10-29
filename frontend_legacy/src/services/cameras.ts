import { fetchApi } from './api';
import type { Camera, CameraPipelineResponse, Observation } from '../types/api';

export const camerasService = {
  async getCameras(): Promise<Camera[]> {
    return fetchApi<Camera[]>('/cameras', { method: 'GET' });
  },

  async createCamera(data: { name: string; source_uri: string }): Promise<Camera> {
    return fetchApi<Camera>('/cameras', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async updateCamera(id: number, data: { name?: string; source_uri?: string }): Promise<Camera> {
    return fetchApi<Camera>(`/cameras/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    });
  },

  async deleteCamera(id: number): Promise<void> {
    return fetchApi<void>(`/cameras/${id}`, { method: 'DELETE' });
  },

  async startCamera(id: number): Promise<CameraPipelineResponse> {
    return fetchApi<CameraPipelineResponse>(`/cameras/${id}/start`, { method: 'POST' });
  },

  async stopCamera(id: number): Promise<CameraPipelineResponse> {
    return fetchApi<CameraPipelineResponse>(`/cameras/${id}/stop`, { method: 'POST' });
  },

  async getCamera(id: number): Promise<Camera> {
    return fetchApi<Camera>(`/cameras/${id}`, { method: 'GET' });
  },

  async getCameraObservations(id: number): Promise<Observation[]> {
    return fetchApi<Observation[]>(`/cameras/${id}/observations`, { method: 'GET' });
  }
};
