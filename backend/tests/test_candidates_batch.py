"""批写入：全合法才写入 / 任一非法整批失败 / 批后旧方案钉死，再排才现算。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.models import Candidate, Hall
from app.services.seed import seed_if_empty

SEED_COUNT = 12


@pytest.fixture()
def client():
    # Fresh, seeded DB per test; skip lifespan so seeding stays under our control.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    return TestClient(app)


def _batch(items):
    return {"candidates": items}


def _valid(i):
    return {"hall_id": 1, "name": f"新生{i}", "ticket_no": f"N{9000 + i}", "paper_id": 1 + (i % 3)}


def _tickets(client):
    return {c["ticket_no"] for c in client.get("/api/candidates").json()}


def test_valid_batch_writes_all(client):
    before = _tickets(client)
    res = client.post("/api/candidates/batch", json=_batch([_valid(1), _valid(2), _valid(3)]))
    assert res.status_code == 201, res.text
    assert len(res.json()) == 3
    after = _tickets(client)
    assert len(after) == len(before) + 3
    assert {f"N{9000 + i}" for i in (1, 2, 3)} <= after


def test_one_illegal_row_fails_whole_batch(client):
    before = _tickets(client)
    items = [_valid(1), {**_valid(2), "paper_id": 999}, _valid(3)]
    res = client.post("/api/candidates/batch", json=_batch(items))
    assert res.status_code == 422
    assert _tickets(client) == before  # 整批失败，禁止只写进一半人


def test_duplicate_ticket_inside_batch_zero_writes(client):
    before = _tickets(client)
    dup = {**_valid(2), "ticket_no": "N9001"}
    res = client.post("/api/candidates/batch", json=_batch([_valid(1), dup]))
    assert res.status_code == 422
    assert _tickets(client) == before


def test_duplicate_ticket_against_roster_zero_writes(client):
    before = _tickets(client)
    clash = {**_valid(1), "ticket_no": "T2026001"}  # 种子已有
    res = client.post("/api/candidates/batch", json=_batch([clash, _valid(2)]))
    assert res.status_code == 422
    assert _tickets(client) == before


def test_failed_batch_leaves_plan_and_stats_untouched(client):
    plan = client.post("/api/seating/run?hall_id=1").json()
    stats_before = client.get("/api/seating/stats?hall_id=1").json()
    res = client.post("/api/candidates/batch", json=_batch([_valid(1), {**_valid(2), "hall_id": 999}]))
    assert res.status_code == 422
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert latest["id"] == plan["id"]
    assert latest["assignments"] == plan["assignments"]
    assert client.get("/api/seating/stats?hall_id=1").json() == stats_before


def test_successful_batch_keeps_old_plan_pinned_until_rerun(client):
    plan = client.post("/api/seating/run?hall_id=1").json()
    stats_before = client.get("/api/seating/stats?hall_id=1").json()

    res = client.post("/api/candidates/batch", json=_batch([_valid(1), _valid(2)]))
    assert res.status_code == 201

    # 批成功后旧图仍钉死：名单变了，但方案与统计保持批前
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert latest["id"] == plan["id"]
    assert latest["assignments"] == plan["assignments"]
    assert client.get("/api/seating/stats?hall_id=1").json() == stats_before
    assert not {"N9001", "N9002"} & {a["ticket_no"] for a in latest["assignments"]}

    # 只有再次点排座才按新名单现算
    new_plan = client.post("/api/seating/run?hall_id=1").json()
    assert new_plan["id"] != plan["id"]
    covered = {a["ticket_no"] for a in new_plan["assignments"]}
    covered |= {u["ticket_no"] for u in new_plan["unplaced"]}
    assert {"N9001", "N9002"} <= covered
    assert client.get("/api/seating/latest?hall_id=1").json()["id"] == new_plan["id"]


def test_seed_batch_with_duplicate_ticket_zero_writes():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db, roster=[("甲", "T1"), ("乙", "T1"), ("丙", "T3")])
        assert db.scalar(select(func.count()).select_from(Candidate)) == 0
        assert db.scalar(select(func.count()).select_from(Hall)) == 0  # 整批零写入
        # 合法种子批重试可正常写入
        seed_if_empty(db)
        assert db.scalar(select(func.count()).select_from(Candidate)) == SEED_COUNT
    finally:
        db.close()
