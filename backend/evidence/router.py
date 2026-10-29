"""
backend/evidence/router.py

Evidence package management endpoints.

  GET  /incidents/{id}/evidence                 — list evidence packages for an incident
  POST /incidents/{id}/evidence                 — package and sign an evidence clip
  GET  /incidents/{id}/evidence/{pkg_id}/verify — verify clip integrity + signature
"""
import hashlib
import hmac
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.auth.jwt import get_current_user, require_role
from backend.db.database import get_db
from backend.db.models import EvidencePackage, Incident, Camera, Observation
from backend.config import EVIDENCE_DIR
from backend.evidence import sign as sign_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["evidence"])

_HMAC_SECRET = os.getenv("EVIDENCE_HMAC_SECRET", "INSECURE-CHANGE-IN-PROD").encode()


# ── Schemas ───────────────────────────────────────────────────────────────────

class EvidencePackageOut(BaseModel):
    id: int
    incident_id: int
    clip_path: str
    has_original: bool
    manifest_hash: str
    signature: str
    ed25519_signature: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class VerifyResult(BaseModel):
    evidence_id: int
    clip_present: bool
    hash_matches: bool
    ed25519_valid: Optional[bool]
    intact: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_incident_or_404(db: Session, incident_id: int) -> Incident:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if inc is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return inc


def _hmac_sign(digest: str) -> str:
    return hmac.new(_HMAC_SECRET, digest.encode(), hashlib.sha256).hexdigest()


# ── List evidence packages ────────────────────────────────────────────────────

@router.get("/incidents/{incident_id}/evidence", response_model=list[EvidencePackageOut])
def list_evidence(
    incident_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator", "responder")),
):
    """Return all evidence packages for an incident."""
    _get_incident_or_404(db, incident_id)
    packages = (
        db.query(EvidencePackage)
        .filter(EvidencePackage.incident_id == incident_id)
        .order_by(EvidencePackage.created_at.desc())
        .all()
    )
    return [
        EvidencePackageOut(
            id=p.id,
            incident_id=p.incident_id,
            clip_path=p.clip_path,
            has_original=bool(p.original_clip_path),
            manifest_hash=p.manifest_hash,
            signature=p.signature,
            ed25519_signature=p.ed25519_signature,
            created_at=p.created_at,
        )
        for p in packages
    ]


# ── Package evidence ──────────────────────────────────────────────────────────

@router.post(
    "/incidents/{incident_id}/evidence",
    response_model=EvidencePackageOut,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_package(
    incident_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    """Create a placeholder evidence package for an incident.

    In a full implementation this would capture the rolling video buffer.
    For this prototype it creates a signed manifest record.
    """
    _get_incident_or_404(db, incident_id)

    clip_path = str(EVIDENCE_DIR / f"incident_{incident_id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.mp4")
    # Use empty-content digest for placeholder when no clip file exists yet
    digest = hashlib.sha256(clip_path.encode()).hexdigest()
    hmac_sig = _hmac_sign(digest)

    try:
        ed25519_sig = sign_module.sign_digest(digest)
    except Exception as exc:
        logger.error("Ed25519 signing failed: %s", exc)
        ed25519_sig = None

    pkg = EvidencePackage(
        incident_id=incident_id,
        clip_path=clip_path,
        manifest_hash=digest,
        signature=hmac_sig,
        ed25519_signature=ed25519_sig,
        created_at=datetime.utcnow(),
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)

    return EvidencePackageOut(
        id=pkg.id,
        incident_id=pkg.incident_id,
        clip_path=pkg.clip_path,
        has_original=bool(pkg.original_clip_path),
        manifest_hash=pkg.manifest_hash,
        signature=pkg.signature,
        ed25519_signature=pkg.ed25519_signature,
        created_at=pkg.created_at,
    )


# ── Verify evidence ───────────────────────────────────────────────────────────

@router.get("/incidents/{incident_id}/evidence/{evidence_id}/verify", response_model=VerifyResult)
def verify_evidence(
    incident_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator", "responder")),
):
    """Verify integrity and signatures of an evidence package."""
    _get_incident_or_404(db, incident_id)
    pkg = db.query(EvidencePackage).filter(
        EvidencePackage.id == evidence_id,
        EvidencePackage.incident_id == incident_id,
    ).first()
    if pkg is None:
        raise HTTPException(status_code=404, detail=f"Evidence package {evidence_id} not found")

    clip_present = Path(pkg.clip_path).exists()

    # Recompute digest from clip file if present, else from path string (placeholder)
    if clip_present:
        digest = hashlib.sha256(Path(pkg.clip_path).read_bytes()).hexdigest()
    else:
        digest = hashlib.sha256(pkg.clip_path.encode()).hexdigest()

    hash_matches = digest == pkg.manifest_hash

    ed25519_valid: Optional[bool] = None
    if pkg.ed25519_signature:
        try:
            ed25519_valid = sign_module.verify_digest(pkg.manifest_hash, pkg.ed25519_signature)
        except Exception:
            ed25519_valid = False

    intact = hash_matches and (ed25519_valid is not False)

    return VerifyResult(
        evidence_id=evidence_id,
        clip_present=clip_present,
        hash_matches=hash_matches,
        ed25519_valid=ed25519_valid,
        intact=intact,
    )
