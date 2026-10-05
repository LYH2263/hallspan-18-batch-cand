import os

# The app builds its engine at import time from settings; tests override get_db
# with SQLite, so point the unused default engine at SQLite before importing app.
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Candidate, Hall, PaperSet, SeatPlan


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()

    hall = Hall(id=1, code="H101", name="一号考室", rows=5, cols=6, min_manhattan=2)
    db.add(hall)
    for i, (code, title) in enumerate(
        [("P-A", "语文 A 卷"), ("P-B", "语文 B 卷"), ("P-C", "语文 C 卷")]
    ):
        db.add(PaperSet(id=i + 1, code=code, title=title))
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass  # session is shared; closed by the fixture

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def count_candidates(db) -> int:
    from sqlalchemy import func, select
    return db.scalar(select(func.count()).select_from(Candidate)) or 0


def count_plans(db) -> int:
    from sqlalchemy import func, select
    return db.scalar(select(func.count()).select_from(SeatPlan)) or 0
