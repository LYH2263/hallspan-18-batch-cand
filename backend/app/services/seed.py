from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import Candidate, Hall, PaperSet
from app.services.candidate_batch import BatchInvalid, CandidateIn, insert_candidate_batch

DEFAULT_ROSTER: list[tuple[str, str]] = [
    ("陈一", "T2026001"), ("李二", "T2026002"), ("张三", "T2026003"), ("赵四", "T2026004"),
    ("钱五", "T2026005"), ("孙六", "T2026006"), ("周七", "T2026007"), ("吴八", "T2026008"),
    ("郑九", "T2026009"), ("王十", "T2026010"), ("冯十一", "T2026011"), ("陈十二", "T2026012"),
]

DEFAULT_PAPERS: list[tuple[str, str]] = [("P-A", "语文 A 卷"), ("P-B", "语文 B 卷"), ("P-C", "语文 C 卷")]


def seed_if_empty(db: Session, roster: list[tuple[str, str]] | None = None) -> None:
    """Seed hall/papers/candidates as ONE atomic batch.

    种子一批混入重复准考证号（或任何非法行）→ 整批零写入，考室/试卷一并回滚，
    不留半批数据；下次启动会重试。
    """
    if (db.scalar(select(func.count()).select_from(Hall)) or 0) > 0:
        return
    roster = DEFAULT_ROSTER if roster is None else roster
    hall = Hall(code="H101", name="一号考室", rows=5, cols=6, min_manhattan=2)
    db.add(hall)
    db.flush()
    paper_ids = []
    for code, title in DEFAULT_PAPERS:
        p = PaperSet(code=code, title=title)
        db.add(p)
        db.flush()
        paper_ids.append(p.id)
    items = [
        CandidateIn(hall_id=hall.id, name=name, ticket_no=ticket,
                    paper_id=paper_ids[i % len(paper_ids)])
        for i, (name, ticket) in enumerate(roster)
    ]
    try:
        insert_candidate_batch(db, items)
    except BatchInvalid:
        db.rollback()
        return
    db.commit()
