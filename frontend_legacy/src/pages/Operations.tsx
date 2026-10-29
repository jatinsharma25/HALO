import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { camerasService } from '../services/cameras';
import type { Camera, Observation } from '../types/api';
import { API_BASE_URL } from '../services/api';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import './Operations.css';

const badgeVariant = (status: Camera['status']) =>
  status === 'active' ? 'success' : status === 'offline' ? 'error' : 'muted';

export const Operations: React.FC = () => {
  const { token } = useAuth();
  const navigate = useNavigate();

  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [streamErrors, setStreamErrors] = useState<Record<number, boolean>>({});
  const [observations, setObservations] = useState<Observation[]>([]);

  useEffect(() => {
    fetchCameras();
    const interval = setInterval(fetchCameras, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedCameraId === null) return;
    fetchObservations(selectedCameraId);
    const interval = setInterval(() => fetchObservations(selectedCameraId), 5000);
    return () => clearInterval(interval);
  }, [selectedCameraId]);

  const fetchCameras = async () => {
    try {
      const data = await camerasService.getCameras();
      setCameras(data);
      setSelectedCameraId(prev =>
        prev !== null && data.some(c => c.id === prev) ? prev : (data[0]?.id ?? null)
      );
    } catch (err) {
      console.error('Failed to fetch cameras:', err);
    }
  };

  const fetchObservations = async (id: number) => {
    try {
      setObservations(await camerasService.getCameraObservations(id));
    } catch (err) {
      console.error('Failed to fetch observations:', err);
      setObservations([]);
    }
  };

  const toggleCamera = async (cam: Camera) => {
    setPendingId(cam.id);
    setStreamErrors(prev => ({ ...prev, [cam.id]: false }));
    try {
      const response = cam.status === 'active'
        ? await camerasService.stopCamera(cam.id)
        : await camerasService.startCamera(cam.id);
      setCameras(prev => prev.map(c => (c.id === cam.id ? { ...c, status: response.status as Camera['status'] } : c)));
    } catch (err) {
      console.error('Failed to toggle camera:', err);
    } finally {
      setPendingId(null);
    }
  };

  const selectedCamera = cameras.find(c => c.id === selectedCameraId) ?? null;
  const activeCameras = cameras.filter(c => c.status === 'active').length;

  const personCount = observations.filter(o => o.event_type?.toLowerCase().includes('person')).length;
  const avgConfidence = observations.length > 0
    ? Math.round((observations.reduce((sum, o) => sum + (o.confidence_score ?? 0), 0) / observations.length) * 100)
    : null;
  const activeTrackCount = new Set(observations.slice(0, 10).map(o => o.track_id)).size;
  const recentEvents = [...observations]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 10);

  return (
    <div className="operations-page">
      <div className="ops-page-header">
        <div className="ops-header-info">
          <h1 className="ops-title">Live Operations</h1>
          <p className="ops-subtitle">{activeCameras} of {cameras.length} cameras active</p>
        </div>
        <div className="ops-header-status">
          <span className="ops-status-dot" />
          Live
        </div>
      </div>

      <div className="operations-content">
        <div className="cam-sidebar">
          <div className="cam-sidebar-label">Cameras</div>
          <div className="camera-list">
            {cameras.length === 0 ? (
              <div className="cam-empty">No cameras configured.</div>
            ) : (
              cameras.map(cam => (
                <div
                  key={cam.id}
                  className={`camera-item${cam.id === selectedCameraId ? ' selected' : ''}`}
                  onClick={() => setSelectedCameraId(cam.id)}
                >
                  <div className="camera-info">
                    <span className="camera-name">{cam.name}</span>
                    <span className="camera-id-label">#{cam.id} · {cam.source_uri}</span>
                  </div>
                  <Badge variant={badgeVariant(cam.status)}>{cam.status}</Badge>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="ops-main-area">
          <div className="ops-feed-row">
            {cameras.length === 0 ? (
              <div className="cam-empty">No cameras configured yet — add one in Configuration.</div>
            ) : (
              cameras.map(cam => (
                <div
                  key={cam.id}
                  className={`feed-card${cam.id === selectedCameraId ? ' selected' : ''}`}
                >
                  <div className="feed-header">
                    <div className="feed-header-info">
                      <h3 className="feed-title">{cam.name}</h3>
                      <span className="feed-source">{cam.source_uri}</span>
                    </div>
                    <div className="feed-header-actions">
                      <Badge variant={badgeVariant(cam.status)}>{cam.status.toUpperCase()}</Badge>
                      <Button
                        variant={cam.status === 'active' ? 'danger' : 'primary'}
                        size="sm"
                        isLoading={pendingId === cam.id}
                        onClick={() => toggleCamera(cam)}
                      >
                        {cam.status === 'active' ? 'Stop' : 'Start'}
                      </Button>
                    </div>
                  </div>
                  <div className="feed-content" onClick={() => setSelectedCameraId(cam.id)}>
                    {cam.status === 'active' ? (
                      streamErrors[cam.id] ? (
                        <div className="feed-placeholder">
                          <p>Stream unavailable</p>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={e => {
                              e.stopPropagation();
                              setStreamErrors(prev => ({ ...prev, [cam.id]: false }));
                            }}
                          >
                            Retry
                          </Button>
                        </div>
                      ) : (
                        <img
                          className="feed-img"
                          src={`${API_BASE_URL}/stream/${cam.id}?token=${token}`}
                          alt={`${cam.name} live feed`}
                          onError={() => setStreamErrors(prev => ({ ...prev, [cam.id]: true }))}
                        />
                      )
                    ) : (
                      <div className="feed-placeholder">
                        <h3>Camera Offline</h3>
                        <p>Start this camera to view its live feed.</p>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="ops-activity-section">
            <div className="ops-activity-header">
              <span className="ops-activity-title">
                Recent Events{selectedCamera ? ` — ${selectedCamera.name}` : ''}
              </span>
              <span className="ops-activity-count">{recentEvents.length}</span>
            </div>
            <div className="obs-table">
              <div className="obs-table-header">
                <span>Time</span>
                <span>Event</span>
                <span>Zone</span>
                <span>Confidence</span>
                <span>Impact</span>
              </div>
              {!selectedCamera ? (
                <div className="obs-empty">Select a camera to view events.</div>
              ) : recentEvents.length === 0 ? (
                <div className="obs-empty">No events recorded for this camera yet.</div>
              ) : (
                recentEvents.map(ev => {
                  const impactLevel = ev.impact_score >= 0.7 ? 'high' : ev.impact_score >= 0.4 ? 'medium' : 'low';
                  return (
                    <div
                      key={ev.id}
                      className="obs-table-row"
                      onClick={() => navigate(`/incidents?camera=${selectedCameraId}`)}
                    >
                      <span className="obs-time">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      <span className="obs-event">{ev.event_type}</span>
                      <span className="obs-zone">{ev.zone_id ?? '—'}</span>
                      <span className="obs-confidence">{Math.round(ev.confidence_score * 100)}%</span>
                      <span className={`obs-impact ${impactLevel}`}>{impactLevel}</span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        <div className="analytics-panel">
          <div className="analytics-panel-header">
            <span className="analytics-panel-title">Live Analytics</span>
            {selectedCamera ? (
              <span className="analytics-cam-name">{selectedCamera.name}</span>
            ) : (
              <span className="analytics-no-cam">No camera selected</span>
            )}
          </div>
          <div className="analytics-section">
            <div className="analytics-status-row">
              <span className={`analytics-status-dot${selectedCamera?.status === 'active' ? ' active' : ''}`} />
              <span className="analytics-status-text">
                {selectedCamera ? selectedCamera.status.toUpperCase() : '—'}
              </span>
            </div>
          </div>
          <div className="analytics-section">
            <div className="analytics-section-label">Metrics</div>
            <div className="analytics-metrics">
              <div className="analytics-metric">
                <span className="analytics-metric-label">People Detected</span>
                <span className="analytics-metric-value">{selectedCamera ? personCount : '—'}</span>
              </div>
              <div className="analytics-metric">
                <span className="analytics-metric-label">Events Total</span>
                <span className="analytics-metric-value">{selectedCamera ? observations.length : '—'}</span>
              </div>
              <div className="analytics-metric">
                <span className="analytics-metric-label">AI Confidence</span>
                <span className="analytics-metric-value analytics-confidence">
                  {selectedCamera && avgConfidence !== null ? `${avgConfidence}%` : '—'}
                </span>
              </div>
              <div className="analytics-metric">
                <span className="analytics-metric-label">Active Tracks</span>
                <span className="analytics-metric-value">{selectedCamera ? activeTrackCount : '—'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
