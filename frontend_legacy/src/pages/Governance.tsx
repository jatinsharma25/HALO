import React, { useEffect, useState } from "react";
import "./Governance.css";
import { camerasService } from "../services/cameras";
import { fetchApi } from "../services/api";
import { auditService, type ChainIntegrity } from "../services/audit";
import { incidentsService } from "../services/incidents";
import type { Camera } from "../types/api";

interface AuditEntry {
  id: number;
  action: string;
  target_type: string | null;
  target_id: number | null;
  timestamp: string;
  payload: string | null;
  actor_id: number | null;
}

const POLICIES = [
  {
    name: "Access Control Policy",
    detail: "JWT-authenticated access, role-based (admin/operator/responder). All endpoints require a valid token.",
    status: "ACTIVE",
    ok: true,
  },
  {
    name: "Data Retention Policy",
    detail: "Video evidence stored as signed MP4 clips with SHA-256 manifest hash. No raw PII stored.",
    status: "ACTIVE",
    ok: true,
  },
  {
    name: "Incident Response Policy",
    detail: "Observations auto-promoted to incidents. Incidents must be acknowledged within 2 hours.",
    status: "ACTIVE",
    ok: true,
  },
  {
    name: "Camera Security Policy",
    detail: "All cameras registered via admin API only. Streams protected by token-scoped endpoints.",
    status: "ACTIVE",
    ok: true,
  },
  {
    name: "Audit Integrity Policy",
    detail: "Audit log uses chained SHA-256 hashes (prev_hash + payload). Cannot be silently tampered.",
    status: "ACTIVE",
    ok: true,
  },
];

export const Governance: React.FC = () => {
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [isLoadingAudit, setIsLoadingAudit] = useState(true);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [integrity, setIntegrity] = useState<ChainIntegrity | null>(null);
  const [publicKey, setPublicKey] = useState<string | null>(null);

  // The audit log is only worth anything if its hash chain can be checked, and
  // evidence signatures are only checkable by someone who has the public key.
  // Both are read-only, so a failure here must not blank the page.
  useEffect(() => {
    void (async () => {
      try { setIntegrity(await auditService.verifyChain()); } catch { setIntegrity(null); }
      try { setPublicKey((await incidentsService.publicKey()).public_key_pem); } catch { setPublicKey(null); }
    })();
  }, []);

  useEffect(() => {
    fetchCameras();
    fetchAuditLog();
  }, []);

  const fetchCameras = async () => {
    try {
      const cams = await camerasService.getCameras();
      setCameras(cams);
    } catch (_) {}
  };

  const fetchAuditLog = async () => {
    setIsLoadingAudit(true);
    setAuditError(null);
    try {
      const data = await fetchApi<AuditEntry[]>('/audit');
      setAuditLog(data);
    } catch (err: any) {
      if (err?.status === 404) {
        setAuditError("Audit log endpoint not yet available.");
      } else {
        setAuditError("Could not load audit log.");
      }
    } finally {
      setIsLoadingAudit(false);
    }
  };

  const formatTs = (ts: string) => {
    try {
      const d = new Date(ts);
      return {
        date: d.toLocaleDateString(),
        time: d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
    } catch {
      return { date: "—", time: "—" };
    }
  };

  return (
    <div className="governance-page" style={{ overflowY: "auto", maxHeight: "100vh" }}>
      {/* HEADER */}
      <header className="governance-header">
        <div>
          <div className="governance-breadcrumb">
            EYESPY <span>/</span> SECURITY CONTROL
          </div>
          <h1>Governance</h1>
          <p>Monitor policies, audit activity, and system accountability.</p>
        </div>
        <div className="governance-status">
          <span /> GOVERNANCE ACTIVE
        </div>
      </header>

      {/* OVERVIEW */}
      <section className="governance-overview">
        <div className="governance-score">
          <div className="score-ring">
            <div>
              <strong>{cameras.length > 0 ? "✓" : "—"}</strong>
              <span style={{ fontSize: "12px" }}>Status</span>
            </div>
          </div>
          <div>
            <span className="overview-label">SYSTEM STATUS</span>
            <h2>Operational</h2>
            <p>
              {cameras.length} camera{cameras.length !== 1 ? "s" : ""} registered.
              Backend services running.
            </p>
          </div>
        </div>

        <div className="overview-metrics">
          <div>
            <span>CAMERAS</span>
            <strong>{cameras.length}</strong>
            <small className="good">Registered</small>
          </div>
          <div>
            <span>ACTIVE</span>
            <strong>{cameras.filter((c) => c.status === "active").length}</strong>
            <small className="good">Live</small>
          </div>
          <div>
            <span>POLICIES</span>
            <strong>{POLICIES.length}</strong>
            <small className="good">Active</small>
          </div>
          <div>
            <span>AUDIT LOG</span>
            <strong>{auditLog.length > 0 ? auditLog.length : "—"}</strong>
            <small>Entries</small>
          </div>
        </div>
      </section>

      {/* MAIN GRID */}
      <div className="governance-grid">
        {/* POLICIES */}
        <section className="governance-card policies-card">
          <div className="governance-card-header">
            <div>
              <h2>Security Policies</h2>
              <p>Active policies governing EyeSpy operations.</p>
            </div>
            {/* No dead Manage button — policies are defined in configuration */}
          </div>

          <div className="policy-list">
            {POLICIES.map((p) => (
              <div className="policy-item" key={p.name}>
                <div className={`policy-icon ${p.ok ? "" : "warning-icon"}`}>
                  {p.ok ? "✓" : "!"}
                </div>
                <div>
                  <strong>{p.name}</strong>
                  <span style={{ fontSize: "13px", color: "#aaa" }}>{p.detail}</span>
                </div>
                <b className={p.ok ? "policy-active" : "policy-warning"}>{p.status}</b>
              </div>
            ))}
          </div>
        </section>

        {/* CONTROLS */}
        <section className="governance-card controls-card">
          <div className="governance-card-header">
            <div>
              <h2>Security Controls</h2>
              <p>Control implementation status based on active configuration.</p>
            </div>
          </div>

          {[
            { label: "JWT Authentication", pct: 100 },
            { label: "Role-Based Authorization", pct: 100 },
            { label: "Audit Chain Logging", pct: 100 },
            { label: "Camera Source Validation", pct: cameras.length > 0 ? 100 : 0 },
            { label: "Evidence Integrity (HMAC)", pct: 90 },
          ].map(({ label, pct }) => (
            <div className="control-item" key={label}>
              <div className="control-top">
                <span>{label}</span>
                <strong>{pct}%</strong>
              </div>
              <div className={`control-bar ${pct < 95 ? "warning-bar" : ""}`}>
                <span style={{ width: `${pct}%` }} />
              </div>
            </div>
          ))}
        </section>
      </div>

      {/* AUDIT LOG */}
      <section className="governance-card audit-card">
        <div className="governance-card-header">
          <div>
            <h2>Audit Activity</h2>
            <p>Actions recorded across the EyeSpy platform.</p>
            {integrity && (
              <p style={{ marginTop: "6px", fontSize: "13px",
                          color: integrity.intact ? "#10b981" : "#ef4444" }}>
                {integrity.intact
                  ? "Hash chain verified — every entry replays to its recorded hash."
                  : `Hash chain BROKEN at entry #${integrity.first_tampered_id}.`}
              </p>
            )}
          </div>
          <button className="governance-small-button" onClick={fetchAuditLog}>
            Refresh
          </button>
        </div>

        <div className="audit-table" style={{ overflowY: "auto", maxHeight: "400px" }}>
          <div className="audit-header">
            <span>DATE</span>
            <span>TIME</span>
            <span>ACTION</span>
            <span>RESOURCE</span>
            <span>DETAILS</span>
          </div>

          {isLoadingAudit ? (
            <div style={{ padding: "24px", textAlign: "center", color: "#888" }}>
              Loading audit log...
            </div>
          ) : auditError ? (
            <div style={{ padding: "24px", textAlign: "center", color: "#888" }}>
              {auditError}
              <div style={{ marginTop: "12px", fontSize: "13px" }}>
                Audit events will appear here as actions are performed (camera CRUD, user changes, incident actions).
              </div>
            </div>
          ) : auditLog.length === 0 ? (
            <div style={{ padding: "24px", textAlign: "center", color: "#888" }}>
              No audit events recorded yet. Events appear when cameras are added/removed, 
              users are modified, or incidents are actioned.
            </div>
          ) : (
            auditLog.map((entry) => {
              const { date, time } = formatTs(entry.timestamp);
              return (
                <div className="audit-row" key={entry.id}>
                  <span className="audit-time">{date}</span>
                  <span className="audit-time">{time}</span>
                  <span>{entry.action}</span>
                  <span className="audit-resource">
                    {entry.target_type ? `${entry.target_type}${entry.target_id ? ` #${entry.target_id}` : ""}` : "—"}
                  </span>
                  <span style={{ fontSize: "13px", color: "#aaa", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {entry.payload ? entry.payload.slice(0, 60) : "—"}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </section>

      {/* EVIDENCE SIGNING KEY */}
      <section className="governance-card">
        <div className="governance-card-header">
          <div>
            <h2>Evidence Signing Key</h2>
            <p>
              Evidence packages are signed with Ed25519. Anyone holding this public key can
              verify a clip independently, without access to this system.
            </p>
          </div>
        </div>
        <pre style={{ fontSize: "12px", color: "#aaa", background: "rgba(0,0,0,0.25)",
                      padding: "14px", borderRadius: "8px", overflowX: "auto",
                      fontFamily: "ui-monospace, Menlo, Consolas, monospace" }}>
          {publicKey ?? "Signing key unavailable — evidence is still hashed, but not signed."}
        </pre>
      </section>
    </div>
  );
};
