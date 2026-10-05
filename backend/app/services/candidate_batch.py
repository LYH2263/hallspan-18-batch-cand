"""Batch candidate intake: validate the whole batch first, then write atomically.

Rules:
- Every row must be valid (non-empty name/ticket, existing hall & paper).
- Ticket numbers must be unique both inside the batch and against the DB.
- If any row is illegal the entire batch fails: zero rows are written and the
  existing seat plan / stats stay exactly as they were before the request.
- A successful write NEVER triggers a reseating. The current SeatPlan stays
  pinned; new candidates only appear after an explicit POST /seating/run.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Candidate, Hall, PaperSet


class BatchError(Exception):
    """Raised when a batch contains any illegal row. Nothing is written."""

    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


def _row_error(index: int, ticket_no: str | None, message: str) -> dict:
    return {"index": index, "ticket_no": ticket_no, "message": message}


def submit_batch(db: Session, rows: list[dict]) -> list[Candidate]:
    """Validate and insert all rows, or raise BatchError leaving the DB untouched."""
    if not rows:
        raise BatchError("批次为空，未写入任何考生", [])

    # ---- Resolve references once up front -----------------------------------
    hall_ids = {r.id for r in db.scalars(select(Hall)).all()}
    papers = db.scalars(select(PaperSet)).all()
    paper_id_by_code = {p.code: p.id for p in papers}
    paper_ids = set(paper_id_by_code.values())

    errors: list[dict] = []
    seen_tickets: set[str] = set()
    prepared: list[dict] = []

    for i, row in enumerate(rows):
        name = (row.get("name") or "").strip()
        ticket_no = (row.get("ticket_no") or "").strip()

        if not name:
            errors.append(_row_error(i, ticket_no or None, "姓名为空"))
        if not ticket_no:
            errors.append(_row_error(i, None, "准考证号为空"))

        # Paper: accept explicit paper_id, otherwise resolve paper_code.
        paper_id = row.get("paper_id")
        if paper_id is None:
            code = (row.get("paper_code") or "").strip()
            if not code:
                errors.append(_row_error(i, ticket_no or None, "缺少试卷套"))
            elif code not in paper_id_by_code:
                errors.append(_row_error(i, ticket_no or None, f"试卷套不存在: {code}"))
            else:
                paper_id = paper_id_by_code[code]
        elif paper_id not in paper_ids:
            errors.append(_row_error(i, ticket_no or None, f"试卷套不存在: {paper_id}"))

        hall_id = row.get("hall_id")
        if hall_id is None:
            errors.append(_row_error(i, ticket_no or None, "缺少考室"))
        elif hall_id not in hall_ids:
            errors.append(_row_error(i, ticket_no or None, f"考室不存在: {hall_id}"))

        # In-batch duplicate ticket — mark every occurrence, write nothing.
        if ticket_no:
            if ticket_no in seen_tickets:
                errors.append(_row_error(i, ticket_no, "批内准考证号重复"))
            else:
                seen_tickets.add(ticket_no)

        prepared.append({"hall_id": hall_id, "name": name,
                         "ticket_no": ticket_no, "paper_id": paper_id})

    # ---- Cross-check tickets against the database ---------------------------
    if seen_tickets:
        existing = set(
            db.scalars(
                select(Candidate.ticket_no).where(Candidate.ticket_no.in_(seen_tickets))
            ).all()
        )
        for i, item in enumerate(prepared):
            if item["ticket_no"] in existing:
                errors.append(_row_error(i, item["ticket_no"], "准考证号已存在"))

    if errors:
        # Whole batch fails — callers roll back; no candidate must be persisted.
        raise BatchError(f"{len(errors)} 条记录非法，整批失败，零写入", errors)

    # ---- All rows legal: insert in one transaction --------------------------
    created = [Candidate(**item) for item in prepared]
    db.add_all(created)
    try:
        db.flush()  # surface the unique constraint inside the same txn
    except Exception as exc:  # pragma: no cover - defensive backstop
        db.rollback()
        raise BatchError("准考证号冲突，整批失败，零写入", []) from exc
    db.commit()
    for c in created:
        db.refresh(c)
    return created
