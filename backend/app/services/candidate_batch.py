"""Atomic batch intake for candidates.

全部合法才写入，任一名非法则整批失败 —— validate the whole batch first;
on any error nothing is written. Successful writes never touch seat plans:
「批写入」与「立刻重排」互斥，旧方案保持钉死，只有再次点排座才按新名单现算。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Candidate, Hall, PaperSet


@dataclass
class CandidateIn:
    hall_id: int
    name: str
    ticket_no: str
    paper_id: int


class BatchInvalid(Exception):
    """Raised when any row in the batch is illegal; carries all error messages."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_candidate_batch(db: Session, items: list[CandidateIn]) -> list[str]:
    """Return every validation error in the batch (empty list = all legal)."""
    errors: list[str] = []
    if not items:
        return ["批为空：至少需要一名考生"]
    seen: dict[str, int] = {}
    for i, it in enumerate(items):
        label = f"第{i + 1}名考生"
        name = (it.name or "").strip()
        ticket = (it.ticket_no or "").strip()
        if not name:
            errors.append(f"{label}：姓名不能为空")
        if not ticket:
            errors.append(f"{label}：准考证号不能为空")
        elif ticket in seen:
            errors.append(f"{label}：准考证号 {ticket} 与第{seen[ticket] + 1}名考生重复")
        else:
            seen[ticket] = i
        if db.get(Hall, it.hall_id) is None:
            errors.append(f"{label}：考室 {it.hall_id} 不存在")
        if db.get(PaperSet, it.paper_id) is None:
            errors.append(f"{label}：试卷 {it.paper_id} 不存在")
    if seen:
        clashes = set(
            db.scalars(select(Candidate.ticket_no).where(Candidate.ticket_no.in_(seen.keys()))).all()
        )
        for t in sorted(clashes):
            errors.append(f"准考证号 {t} 已存在于名册")
    return errors


def insert_candidate_batch(db: Session, items: list[CandidateIn]) -> list[Candidate]:
    """Validate then stage the whole batch in ONE transaction.

    Raises BatchInvalid before writing anything if any row is illegal —
    批失败不得留下部分新考生. Caller decides when to commit; nothing here
    recomputes or invalidates existing seat plans.
    """
    errors = validate_candidate_batch(db, items)
    if errors:
        raise BatchInvalid(errors)
    rows = [
        Candidate(
            hall_id=it.hall_id,
            name=it.name.strip(),
            ticket_no=it.ticket_no.strip(),
            paper_id=it.paper_id,
        )
        for it in items
    ]
    db.add_all(rows)
    db.flush()
    return rows
