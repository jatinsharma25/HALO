import React, { useState, useEffect } from "react";
import "./Configuration.css";
import { camerasService } from "../services/cameras";
import type { Camera } from "../types/api";

export const Configuration: React.FC = () => {
  const [activeTab, setActiveTab] = useState("cameras");
  
  // Cameras State
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCameras();
  }, []);

  const fetchCameras = async () => {
    try {
      setLoading(true);
      const data = await camerasService.getCameras();
      setCameras(data);
    } catch (err) {
      console.error("Failed to fetch cameras:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddCamera = async () => {
    const nameInput = document.getElementById('add-cam-name') as HTMLInputElement;
    const sourceInput = document.getElementById('add-cam-source') as HTMLInputElement;
    if (!nameInput?.value || !sourceInput?.value) {
      alert('Please fill both fields');
      return;
    }
    try {
      await camerasService.createCamera({ name: nameInput.value, source_uri: sourceInput.value });
      nameInput.value = '';
      sourceInput.value = '';
      fetchCameras();
    } catch (err) {
      alert('Failed to add camera');
    }
  };

  const handleEditCamera = async (cam: Camera) => {
    const name = window.prompt("Enter new camera name:", cam.name);
    if (name === null) return;
    const source_uri = window.prompt("Enter new source URI:", cam.source_uri);
    if (source_uri === null) return;
    
    try {
      await camerasService.updateCamera(cam.id, { name, source_uri });
      fetchCameras();
    } catch (err) {
      alert("Failed to update camera");
    }
  };

  const handleDeleteCamera = async (id: number) => {
    if (!window.confirm("Are you sure you want to delete this camera?")) return;
    try {
      await camerasService.deleteCamera(id);
      fetchCameras();
    } catch (err) {
      alert("Failed to delete camera");
    }
  };



  return (
    <div className="config-page">
      <header className="config-header">
        <div>
          <div className="config-breadcrumb">
            EYESPY <span>/</span> SYSTEM
          </div>
          <h1>Configuration</h1>
          <p>Manage Cameras, Zones, Schedules, and Standard Operating Procedures.</p>
        </div>
        
        <div />
      </header>

      <main className="config-layout">
        <aside className="config-sidebar">
          <button className={`config-nav ${activeTab === "cameras" ? "active" : ""}`} onClick={() => setActiveTab("cameras")}>
            <span>▣</span> Cameras
          </button>
          <button className={`config-nav ${activeTab === "zones" ? "active" : ""}`} onClick={() => setActiveTab("zones")}>
            <span>◩</span> Zones
          </button>
          <button className={`config-nav ${activeTab === "schedules" ? "active" : ""}`} onClick={() => setActiveTab("schedules")}>
            <span>⏱</span> Schedules
          </button>
          <button className={`config-nav ${activeTab === "sops" ? "active" : ""}`} onClick={() => setActiveTab("sops")}>
            <span>ℹ</span> SOPs
          </button>
        </aside>

        <div className="config-content">
          {activeTab === "cameras" && (
            <section className="settings-card">
              <div className="settings-heading">
                <div>
                  <div>
                    <h2>Camera Configuration</h2>
                    <p>Manage video sources and device connections.</p>
                  </div>
                </div>
              </div>

              <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', padding: '16px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                <input id="add-cam-name" type="text" placeholder="Camera Name" style={{ padding: '8px', borderRadius: '4px', border: '1px solid #444', background: '#222', color: '#fff', flex: 1 }} />
                <input id="add-cam-source" type="text" placeholder="Source URI (e.g. test.mp4 or 0)" style={{ padding: '8px', borderRadius: '4px', border: '1px solid #444', background: '#222', color: '#fff', flex: 1 }} />
                <button className="small-action" onClick={handleAddCamera}>+ Add Camera</button>
              </div>

              <div className="camera-table">
                <div className="camera-table-header">
                  <span>CAMERA</span>
                  <span>SOURCE</span>
                  <span>STATUS</span>
                  <span>ACTIONS</span>
                  <span />
                </div>

                {loading ? <div style={{padding: '20px', textAlign: 'center'}}>Loading cameras...</div> : 
                 cameras.map((camera) => (
                  <div className="camera-table-row" key={camera.id}>
                    <div className="camera-name">
                      <div className="mini-camera">▣</div>
                      <div>
                        <strong>{camera.name}</strong>
                        <span>ID: {camera.id}</span>
                      </div>
                    </div>
                    <span>{camera.source_uri}</span>
                    <span className={camera.status === "active" ? "camera-online" : "camera-offline"}>
                      <i />{camera.status}
                    </span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button style={{ background: 'transparent', border: '1px solid #444', color: '#fff', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer' }} onClick={() => handleEditCamera(camera)}>Edit</button>
                      <button style={{ background: 'transparent', border: '1px solid #f44336', color: '#f44336', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer' }} onClick={() => handleDeleteCamera(camera.id)}>Delete</button>
                    </div>
                    <span />
                  </div>
                ))}
              </div>
            </section>
          )}

          {activeTab === "zones" && (
            <section className="settings-card">
              <div className="settings-heading">
                <div>
                  <div>
                    <h2>Restricted Zones</h2>
                    <p>Configure spatial monitoring and restrictions.</p>
                  </div>
                </div>
              </div>

              <div style={{ margin: '0 0 20px 0', padding: '12px 16px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.4)', borderRadius: '8px', fontSize: '14px', color: '#f59e0b' }}>
                ⚠ Zone configuration backend API is not yet implemented. These controls are shown for reference only and do not affect the running system.
              </div>

              <div className="setting-row" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <div>
                  <strong>Enable Restricted Zones</strong>
                  <span>Detect unauthorized access in marked areas.</span>
                </div>
                <button className="toggle enabled" disabled>
                  <span />
                </button>
              </div>

              <div className="setting-row" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <div>
                  <strong>After-hours Monitoring</strong>
                  <span>Automatically enforce restrictions outside normal hours.</span>
                </div>
                <button className="toggle enabled" disabled>
                  <span />
                </button>
              </div>

              <div className="slider-setting" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <div className="slider-header">
                  <div>
                    <strong>Loitering Threshold (seconds)</strong>
                    <span>Time before a person triggers a loitering alert.</span>
                  </div>
                  <strong className="slider-value">60s</strong>
                </div>
                <input type="range" min="10" max="300" step="10" defaultValue={60} disabled />
              </div>
            </section>
          )}

          {activeTab === "schedules" && (
            <section className="settings-card">
              <div className="settings-heading">
                <div>
                  <div>
                    <h2>Schedules</h2>
                    <p>Define operational hours and automatic mode switching.</p>
                  </div>
                </div>
              </div>

              <div style={{ margin: '0 0 20px 0', padding: '12px 16px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.4)', borderRadius: '8px', fontSize: '14px', color: '#f59e0b' }}>
                ⚠ Schedule backend API is not yet implemented. These controls are shown for reference only and do not affect the running system.
              </div>

              <div className="setting-row" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <div>
                  <strong>Enable Scheduling</strong>
                  <span>System will follow defined time periods automatically.</span>
                </div>
                <button className="toggle enabled" disabled>
                  <span />
                </button>
              </div>

              <div className="setting-row" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <div>
                  <strong>Start Time</strong>
                  <span>When restricted hours begin (24h).</span>
                </div>
                <input type="time" defaultValue="18:00" disabled style={{ padding: '8px', background: '#222', color: '#fff', border: '1px solid #444', borderRadius: '4px' }} />
              </div>

              <div className="setting-row" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <div>
                  <strong>End Time</strong>
                  <span>When restricted hours end (24h).</span>
                </div>
                <input type="time" defaultValue="06:00" disabled style={{ padding: '8px', background: '#222', color: '#fff', border: '1px solid #444', borderRadius: '4px' }} />
              </div>
            </section>
          )}

          {activeTab === "sops" && (
            <section className="settings-card">
              <div className="settings-heading">
                <div>
                  <div>
                    <h2>Standard Operating Procedures (SOPs)</h2>
                    <p>Guidelines for operators using EyeSpy.</p>
                  </div>
                </div>
              </div>
              
              {/* Item 2 fix: was color:#e0e0e0 (hardcoded near-white, invisible in light mode) */}
              <div style={{ padding: '20px', lineHeight: '1.6', color: 'var(--color-foreground)' }}>
                <ul style={{ listStyleType: 'disc', paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <li><strong>Active Monitoring:</strong> Keep the surveillance console active while monitoring.</li>
                  <li><strong>Status Checks:</strong> Check camera status before beginning monitoring to ensure all feeds are functional.</li>
                  <li><strong>Zone Verification:</strong> Verify restricted zones are correctly configured if coverage changes.</li>
                  <li><strong>Alert Triage:</strong> Review suspicious activity and alerts promptly from the Operations or Incidents view.</li>
                  <li><strong>Escalation:</strong> Escalate incidents according to severity (e.g. Critical impact warrants immediate response).</li>
                  <li><strong>Reconfiguration:</strong> Reset/reconfigure restricted zones when building layout changes.</li>
                  <li><strong>Handover:</strong> Review unresolved alerts before ending a shift.</li>
                </ul>
              </div>
            </section>
          )}

        </div>
      </main>
    </div>
  );
};

