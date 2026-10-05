from sqlalchemy import func, select

from app.models.models import Candidate, SeatPlan


def _row(name, ticket, code="P-A", hall=1):
    return {"name": name, "ticket_no": ticket, "paper_code": code, "hall_id": hall}


def test_valid_batch_inserts_all_and_does_not_reseat(client, db_session):
    # Establish an existing plan first (only 1 seeded candidate via /run).
    db_session.add(Candidate(hall_id=1, name="旧生", ticket_no="OLD1", paper_id=1))
    db_session.commit()
    run = client.post("/api/seating/run?hall_id=1")
    assert run.status_code == 200
    plan_id_before = run.json()["id"]
    assert count_plans(db_session) == 1

    resp = client.post("/api/candidates/batch", json={"candidates": [
        _row("陈一", "T1001"),
        _row("李二", "T1002", "P-B"),
        _row("张三", "T1003", "P-C"),
    ]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] == 3
    assert count_candidates(db_session) == 4

    # A successful batch must NOT create a new plan: old plan stays pinned.
    assert count_plans(db_session) == 1
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert latest["id"] == plan_id_before
    old_names = {a["name"] for a in latest["assignments"]}
    assert "旧生" in old_names
    assert {"陈一", "李二", "张三"}.isdisjoint(old_names)

    # Stats (read off latest plan) also stay at pre-batch values.
    stats = client.get("/api/seating/stats?hall_id=1").json()
    assert stats["seated"] == 1

    # Only an explicit re-run computes with the new roster.
    rerun = client.post("/api/seating/run?hall_id=1").json()
    assert rerun["id"] != plan_id_before
    new_names = {a["name"] for a in rerun["assignments"]}
    assert {"陈一", "李二", "张三"} <= new_names


def test_duplicate_ticket_within_batch_writes_zero(client, db_session):
    before = count_candidates(db_session)
    resp = client.post("/api/candidates/batch", json={"candidates": [
        _row("陈一", "DUP1"),
        _row("李二", "DUP2"),
        _row("张三", "DUP1"),  # duplicate ticket inside the batch
    ]})
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert any("重复" in e["message"] for e in body["errors"])
    # Whole batch rejected — not even the legal rows landed.
    assert count_candidates(db_session) == before
    assert db_session.scalars(select(Candidate.ticket_no)).all() == []
    # No plan created by a failed intake.
    assert count_plans(db_session) == 0


def test_any_illegal_row_fails_whole_batch(client, db_session):
    # Row references a paper and hall that do not exist -> entire batch zero.
    resp = client.post("/api/candidates/batch", json={"candidates": [
        _row("合法", "OK1"),
        {"name": "无卷", "ticket_no": "NO1", "paper_code": "P-Z", "hall_id": 1},
        {"name": "无室", "ticket_no": "NO2", "paper_code": "P-A", "hall_id": 999},
        {"name": "   ", "ticket_no": "NO3", "paper_code": "P-A", "hall_id": 1},
        {"name": "缺证", "ticket_no": "  ", "paper_code": "P-A", "hall_id": 1},
    ]})
    assert resp.status_code == 400
    assert len(resp.json()["errors"]) >= 4
    assert count_candidates(db_session) == 0


def test_ticket_conflict_with_db_writes_zero(client, db_session):
    client.post("/api/candidates/batch", json={"candidates": [_row("旧生", "TK1")]})
    assert count_candidates(db_session) == 1

    resp = client.post("/api/candidates/batch", json={"candidates": [
        _row("新生A", "TK2"),
        _row("新生B", "TK1"),  # collides with an already-stored candidate
    ]})
    assert resp.status_code == 400
    assert any("已存在" in e["message"] for e in resp.json()["errors"])
    # Neither the colliding row nor its legal neighbour was written.
    names = set(db_session.scalars(select(Candidate.name)).all())
    assert names == {"旧生"}


def test_empty_batch_rejected(client, db_session):
    resp = client.post("/api/candidates/batch", json={"candidates": []})
    assert resp.status_code == 400
    assert count_candidates(db_session) == 0


def test_latest_with_no_plan_does_not_auto_compute(client, db_session):
    # Empty hall: reading latest must return an empty skeleton, not run seating.
    resp = client.get("/api/seating/latest?hall_id=1")
    assert resp.status_code == 200
    assert resp.json()["id"] is None
    assert resp.json()["assignments"] == []
    assert count_plans(db_session) == 0


def count_candidates(db) -> int:
    return db.scalar(select(func.count()).select_from(Candidate)) or 0


def count_plans(db) -> int:
    return db.scalar(select(func.count()).select_from(SeatPlan)) or 0
