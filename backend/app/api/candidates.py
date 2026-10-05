from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Candidate
from app.services.candidate_batch import BatchError, submit_batch

router = APIRouter(prefix="/candidates", tags=["candidates"])


class CandidateIn(BaseModel):
    name: str | None = None
    ticket_no: str | None = None
    paper_id: int | None = None
    paper_code: str | None = None
    hall_id: int | None = None


class BatchIn(BaseModel):
    candidates: list[CandidateIn]


@router.get("")
def list_candidates(db: Session = Depends(get_db)):
    return [{"id": r.id, "hall_id": r.hall_id, "name": r.name, "ticket_no": r.ticket_no, "paper_id": r.paper_id}
            for r in db.scalars(select(Candidate).order_by(Candidate.id)).all()]


@router.post("/batch")
def create_batch(payload: BatchIn, db: Session = Depends(get_db)):
    """Atomic batch intake.

    All rows valid -> write all. Any illegal row -> 400 and zero rows written.
    Never runs the seating engine; the current plan stays pinned.
    """
    rows = [c.model_dump() for c in payload.candidates]
    try:
        created = submit_batch(db, rows)
    except BatchError as exc:
        db.rollback()
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": str(exc), "errors": exc.errors},
        )
    return {
        "ok": True,
        "inserted": len(created),
        "candidates": [
            {"id": c.id, "hall_id": c.hall_id, "name": c.name,
             "ticket_no": c.ticket_no, "paper_id": c.paper_id}
            for c in created
        ],
    }
