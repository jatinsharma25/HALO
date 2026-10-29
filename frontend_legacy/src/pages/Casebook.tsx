import React, { useEffect, useState } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import {
  incidentsService,
  INCIDENT_STATUSES,
  type EvidencePackage,
  type EvidenceVerification,
  type Incident,
} from '../services/incidents';
import './Casebook.css';

const toneFor = (status: string): 'success' | 'warning' | 'error' | 'muted' | 'default' => {
  if (status === 'resolved') return 'success';
  if (status === 'escalated') return 'error';
  if (status === 'new') return 'warning';
  return 'muted';
};

export const Casebook: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [filter, setFilter] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [evidence, setEvidence] = useState<EvidencePackage[]>([]);
  const [verifications, setVerifications] = useState<Record<number, EvidenceVerification>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = incidents.find(i => i.id === selectedId) ?? null;

  const loadIncidents = async (status: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const rows = await incidentsService.getIncidents(status || undefined);
      setIncidents(rows);
      if (rows.length && !rows.some(r => r.id === selectedId)) setSelectedId(rows[0].id);
      if (!rows.length) setSelectedId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setIncidents([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { void loadIncidents(filter); }, [filter]);

  const loadEvidence = async (incidentId: number) => {
    try {
      setEvidence(await incidentsService.getEvidence(incidentId));
    } catch {
      setEvidence([]);
    }
  };

  useEffect(() => {
    if (selectedId === null) { setEvidence([]); return; }
    void loadEvidence(selectedId);
  }, [selectedId]);

  const changeStatus = async (next: string) => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await incidentsService.updateStatus(selected.id, next);
      await loadIncidents(filter);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const packageEvidence = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await incidentsService.packageEvidence(selected.id);
      await loadEvidence(selected.id);
      await loadIncidents(filter);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (evidenceId: number) => {
    try {
      const result = await incidentsService.verifyEvidence(evidenceId);
      setVerifications(prev => ({ ...prev, [evidenceId]: result }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—');

  return (
    <div className="casebook-page">
      <header className="casebook-header">
        <div>
          <div className="casebook-eyebrow">EYESPY / CASEBOOK</div>
          <h1>Incidents &amp; Evidence</h1>
        </div>
        <select
          className="casebook-filter"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          aria-label="Filter incidents by status"
        >
          <option value="">All statuses</option>
          {INCIDENT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </header>

      {error && <div className="casebook-error">{error}</div>}

      <div className="casebook-content">
        <Card className="casebook-list">
          <div className="casebook-panel-head"><h2>Incidents</h2></div>
          <div className="casebook-scroll">
            {isLoading ? (
              <div className="casebook-empty">Loading…</div>
            ) : incidents.length === 0 ? (
              <div className="casebook-empty">
                No incidents{filter ? ` with status “${filter}”` : ''}.
              </div>
            ) : (
              incidents.map(i => (
                <button
                  type="button"
                  key={i.id}
                  className={`casebook-item ${selectedId === i.id ? 'is-selected' : ''}`}
                  onClick={() => setSelectedId(i.id)}
                >
                  <div className="casebook-item-top">
                    <strong>Incident #{i.id}</strong>
                    <Badge variant={toneFor(i.status)}>{i.status}</Badge>
                  </div>
                  <div className="casebook-item-meta">
                    {i.observation_count} observation{i.observation_count === 1 ? '' : 's'}
                    {' · '}
                    {i.evidence_count} evidence
                  </div>
                  <div className="casebook-item-meta">{fmt(i.created_at)}</div>
                </button>
              ))
            )}
          </div>
        </Card>

        <Card className="casebook-detail">
          {!selected ? (
            <div className="casebook-empty">Select an incident.</div>
          ) : (
            <div className="casebook-scroll casebook-detail-body">
              <h2>Incident #{selected.id}</h2>

              <div className="casebook-facts">
                <div><span>Status</span><Badge variant={toneFor(selected.status)}>{selected.status}</Badge></div>
                <div><span>Opened</span><strong>{fmt(selected.created_at)}</strong></div>
                <div><span>Window opens</span><strong>{fmt(selected.correlation_window_start)}</strong></div>
                <div><span>Window closes</span><strong>{fmt(selected.correlation_window_end)}</strong></div>
              </div>

              <h3>Advance status</h3>
              <div className="casebook-actions">
                {INCIDENT_STATUSES.filter(s => s !== selected.status).map(s => (
                  <Button key={s} variant="secondary" size="sm" disabled={busy}
                          onClick={() => void changeStatus(s)}>
                    {s}
                  </Button>
                ))}
              </div>

              <div className="casebook-evidence-head">
                <h3>Evidence</h3>
                <Button variant="primary" size="sm" isLoading={busy} onClick={() => void packageEvidence()}>
                  Package clip
                </Button>
              </div>

              {evidence.length === 0 ? (
                <div className="casebook-empty">No evidence packaged yet.</div>
              ) : (
                <ul className="casebook-evidence-list">
                  {evidence.map(p => {
                    const v = verifications[p.id];
                    return (
                      <li key={p.id} className="casebook-evidence">
                        <div className="casebook-item-top">
                          <strong>Package #{p.id}</strong>
                          <span className="casebook-item-meta">{fmt(p.created_at)}</span>
                        </div>
                        {/* The digest is the point of the package, so it is shown
                            rather than hidden behind a detail view. */}
                        <code className="casebook-hash">sha256 {p.manifest_hash}</code>
                        <div className="casebook-actions">
                          <Button variant="ghost" size="sm" onClick={() => void verify(p.id)}>
                            Verify integrity
                          </Button>
                          {v && (
                            <Badge variant={v.intact ? 'success' : 'error'}>
                              {v.intact ? 'intact' : 'TAMPERED'}
                              {v.ed25519_valid === null ? ' · unsigned' : ''}
                            </Badge>
                          )}
                        </div>
                        {v && !v.intact && (
                          <div className="casebook-item-meta">
                            {v.clip_present
                              ? 'The clip on disk no longer matches its recorded digest.'
                              : 'The clip file is missing.'}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
