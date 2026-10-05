from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Candidate
from app.services.candidate_batch import BatchInvalid, CandidateIn, insert_candidate_batch

router = APIRouter(prefix="/candidates", tags=["candidates"])


class CandidateInSchema(BaseModel):
    hall_id: int
    name: str
    ticket_no: str
    paper_id: int


class BatchIn(BaseModel):
    candidates: list[CandidateInSchema]


def _to_dict(r: Candidate) -> dict:
    return {"id": r.id, "hall_id": r.hall_id, "name": r.name, "ticket_no": r.ticket_no, "paper_id": r.paper_id}


@router.get("")
def list_candidates(db: Session = Depends(get_db)):
    return [_to_dict(r)
            for r in db.scalars(select(Candidate).order_by(Candidate.id)).all()]


@router.post("/batch", status_code=201)
def create_candidates_batch(body: BatchIn, db: Session = Depends(get_db)):
    """一批多名考生一次提交：全部合法才写入，任一名非法则整批失败（零写入）。

    成功也只写名册 —— 不回刷、不作废已有座位方案；旧图保持钉死，
    只有再次 POST /seating/run 才按新名单现算。
    """
    items = [CandidateIn(**c.model_dump()) for c in body.candidates]
    try:
        rows = insert_candidate_batch(db, items)
    except BatchInvalid as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=e.errors)
    db.commit()
    return [_to_dict(r) for r in rows]
