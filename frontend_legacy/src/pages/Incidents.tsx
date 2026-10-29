import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { alertsService, type Alert } from '../services/alerts';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

import './Incidents.css';

// The /alerts endpoint already joins the camera name and the acknowledgement,
// so this is the row as the server sends it.
type AlertWithCamera = Alert;

export const Incidents: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const defaultCameraId = searchParams.get('camera');

  const [alerts, setAlerts] = useState<AlertWithCamera[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [ackBusy, setAckBusy] = useState<number | null>(null);

  useEffect(() => {
    fetchAllAlerts();
  }, []);

  const fetchAllAlerts = async () => {
    setIsLoading(true);
    try {
      // One request instead of one per camera: /alerts joins the camera name
      // server-side, so a site with twenty cameras no longer costs twenty
      // round trips and cannot half-load when one of them errors.
      const allAlerts: AlertWithCamera[] = await alertsService.getAlerts({ limit: 200 });

      allAlerts.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setAlerts(allAlerts);

      if (defaultCameraId) {
        const alertForCam = allAlerts.find(a => a.camera_id === Number(defaultCameraId));
        if (alertForCam) setSelectedAlertId(alertForCam.id);
        else if (allAlerts.length > 0) setSelectedAlertId(allAlerts[0].id);
      } else if (allAlerts.length > 0) {
        setSelectedAlertId(allAlerts[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch alerts:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const acknowledgeAlert = async (alertId: number) => {
    setAckBusy(alertId);
    try {
      await alertsService.acknowledge(alertId);
      // Update in place rather than refetching: a refetch would re-sort the
      // list and could move the row the operator is reading.
      setAlerts(prev => prev.map(a => (a.id === alertId ? { ...a, acknowledged: true } : a)));
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    } finally {
      setAckBusy(null);
    }
  };

  const selectedAlert = alerts.find(a => a.id === selectedAlertId);

  const formatDateTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return { date: d.toLocaleDateString(), time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    } catch {
      return { date: 'Unknown Date', time: 'Unknown Time' };
    }
  };

  return (
    <div className="incidents-page" style={{ display: 'flex', flexDirection: 'column', height: '100vh', padding: '24px', boxSizing: 'border-box' }}>
      <header className="incidents-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <div className="text-sm text-muted-foreground" style={{ fontSize: '12px', color: '#888', marginBottom: '4px', letterSpacing: '1px' }}>EYESPY / ALERTS</div>
          <h1 style={{ margin: 0, fontSize: '24px' }}>Incidents & Alerts</h1>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">Operator: {user?.username}</span>
          <Button variant="ghost" size="sm" onClick={() => navigate('/directory')}>Directory</Button>
          {/* Removed duplicate Sign Out */}
        </div>
      </header>

      <div className="incidents-content" style={{ display: 'flex', gap: '24px', flex: 1, minHeight: '0' }}>
        {/* Alerts List Sidebar */}
        <Card style={{ flex: '0 0 350px', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '16px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
            <h2 style={{ margin: 0, fontSize: '16px' }}>Active Alerts</h2>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {isLoading ? (
              <div style={{ textAlign: 'center', color: '#888', padding: '20px' }}>Loading alerts...</div>
            ) : alerts.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#888', padding: '20px' }}>No alerts found.</div>
            ) : (
              alerts.map(alert => {
                const { date, time } = formatDateTime(alert.timestamp);
                const isSelected = selectedAlertId === alert.id;
                const severity = alert.impact_score > 0.8 ? 'CRITICAL' : alert.impact_score > 0.5 ? 'HIGH' : 'LOW';
                const severityColor = severity === 'CRITICAL' ? '#ef4444' : severity === 'HIGH' ? '#f59e0b' : '#3b82f6';

                return (
                  <div 
                    key={alert.id}
                    onClick={() => setSelectedAlertId(alert.id)}
                    style={{ 
                      padding: '12px', borderRadius: '6px', cursor: 'pointer',
                      background: isSelected ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.03)',
                      borderLeft: `4px solid ${severityColor}`,
                      transition: 'background 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <strong style={{ fontSize: '14px' }}>{alert.event_type}</strong>
                      <span style={{ fontSize: '12px', color: '#888' }}>{time}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: '#ccc', marginBottom: '4px' }}>{alert.camera_name}</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#888' }}>
                      <span>{date}</span>
                      <span style={{ color: severityColor, fontWeight: 'bold' }}>{severity}</span>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </Card>

        {/* Incident Details Main Area */}
        <Card style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {selectedAlert ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              <div style={{ padding: '24px', borderBottom: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                  <div>
                    <h2 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>{selectedAlert.event_type}</h2>
                    <div style={{ fontSize: '16px', color: '#ccc' }}>Incident #{selectedAlert.id}</div>
                  </div>
                  <div style={{ padding: '6px 12px', borderRadius: '4px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', fontWeight: 'bold', fontSize: '14px', border: '1px solid #ef4444' }}>
                    STATUS: ACTIVE
                  </div>
                </div>
              </div>
              
              <div style={{ padding: '24px', flex: 1, overflowY: 'auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '24px', marginBottom: '32px' }}>
                  <div>
                    <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px', textTransform: 'uppercase' }}>Camera</div>
                    <div style={{ fontSize: '16px', fontWeight: 500 }}>{selectedAlert.camera_name}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px', textTransform: 'uppercase' }}>Date</div>
                    <div style={{ fontSize: '16px', fontWeight: 500 }}>{formatDateTime(selectedAlert.timestamp).date}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px', textTransform: 'uppercase' }}>Time</div>
                    <div style={{ fontSize: '16px', fontWeight: 500 }}>{formatDateTime(selectedAlert.timestamp).time}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px', textTransform: 'uppercase' }}>AI Confidence</div>
                    <div style={{ fontSize: '16px', fontWeight: 500, color: '#10b981' }}>{Math.round(selectedAlert.confidence_score * 100)}%</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px', textTransform: 'uppercase' }}>Impact</div>
                    <div style={{ fontSize: '16px', fontWeight: 500, color: selectedAlert.impact_score > 0.8 ? '#ef4444' : '#f59e0b' }}>
                      {selectedAlert.impact_score.toFixed(2)} ({selectedAlert.impact_score > 0.8 ? 'CRITICAL' : selectedAlert.impact_score > 0.5 ? 'HIGH' : 'LOW'})
                    </div>
                  </div>
                </div>

                <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {selectedAlert.acknowledged ? (
                    <span style={{ fontSize: '13px', color: '#10b981' }}>
                      Acknowledged{selectedAlert.acknowledged_by_username ? ` by ${selectedAlert.acknowledged_by_username}` : ''}
                      {selectedAlert.acknowledged_at ? ` · ${new Date(selectedAlert.acknowledged_at).toLocaleString()}` : ''}
                    </span>
                  ) : (
                    <>
                      <Button
                        variant="primary"
                        size="sm"
                        isLoading={ackBusy === selectedAlert.id}
                        onClick={() => void acknowledgeAlert(selectedAlert.id)}
                      >
                        Acknowledge
                      </Button>
                      <span style={{ fontSize: '13px', color: '#888' }}>Unacknowledged</span>
                    </>
                  )}
                </div>

                <div style={{ marginBottom: '32px' }}>
                  <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', textTransform: 'uppercase' }}>Description</div>
                  <div style={{ fontSize: '15px', lineHeight: '1.6', background: 'rgba(255,255,255,0.05)', padding: '16px', borderRadius: '8px', overflowWrap: 'break-word' }}>
                    {selectedAlert.explanation || 'No detailed description available.'}
                  </div>
                </div>
                
                {selectedAlert.raw_metadata && (
                  <div>
                    <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', textTransform: 'uppercase' }}>Raw Metadata</div>
                    <pre style={{ fontSize: '13px', background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '8px', overflowX: 'auto', border: '1px solid rgba(255,255,255,0.1)' }}>
                      {selectedAlert.raw_metadata}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#888' }}>
              Select an alert from the list to view details.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

