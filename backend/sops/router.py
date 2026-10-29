"""
backend/sops/router.py

Standard Operating Procedures — the response steps shown alongside an
incident of a matching type.

GET    /sops        — list all (admin, operator, responder)
POST   /sops        — create (admin)
PATCH  /sops/{id}   — update (admin)
DELETE /sops/{id}   — delete (admin)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.jwt import require_role
from backend.db.database import get_db
from backend.db.models import SOP
from backend.audit.chain import audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sops", tags=["sops"])


class SOPCreate(BaseModel):
    incident_type: str
    title: str
    steps_text: str


class SOPUpdate(BaseModel):
    incident_type: Optional[str] = None
    title: Optional[str] = None
    steps_text: Optional[str] = None


class SOPOut(BaseModel):
    id: int
    incident_type: str
    title: str
    steps_text: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[SOPOut])
def list_sops(
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator", "responder")),
):
    return db.query(SOP).order_by(SOP.incident_type).all()


@router.post("", response_model=SOPOut, status_code=201)
def create_sop(
    body: SOPCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    if db.query(SOP).filter(SOP.incident_type == body.incident_type).first():
        raise HTTPException(status_code=409, detail=f"An SOP for '{body.incident_type}' already exists")

    sop = SOP(incident_type=body.incident_type, title=body.title, steps_text=body.steps_text)
    db.add(sop)
    db.commit()
    db.refresh(sop)

    audit_log(db, action="sop.create", actor_id=current_user.id,
              target_type="sop", target_id=sop.id,
              payload={"incident_type": sop.incident_type, "title": sop.title})
    return sop


@router.patch("/{sop_id}", response_model=SOPOut)
def update_sop(
    sop_id: int,
    body: SOPUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(status_code=404, detail=f"SOP {sop_id} not found")

    if body.incident_type is not None:
        sop.incident_type = body.incident_type
    if body.title is not None:
        sop.title = body.title
    if body.steps_text is not None:
        sop.steps_text = body.steps_text
    db.commit()
    db.refresh(sop)

    audit_log(db, action="sop.update", actor_id=current_user.id,
              target_type="sop", target_id=sop.id, payload={"title": sop.title})
    return sop


@router.delete("/{sop_id}", status_code=204)
def delete_sop(
    sop_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(status_code=404, detail=f"SOP {sop_id} not found")
    db.delete(sop)
    db.commit()

    audit_log(db, action="sop.delete", actor_id=current_user.id,
              target_type="sop", target_id=sop_id, payload={})
