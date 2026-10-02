import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, workers
from app.db import Base, get_session
from app.main import app


@pytest.fixture
def database(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # SQLite exercises API behavior only. Real advisory-lock semantics are covered
    # in the opt-in PostgreSQL suite, not asserted by these stand-ins.
    @event.listens_for(engine, "connect")
    def functions(connection, record):
        connection.create_function("pg_try_advisory_lock", 1, lambda key: True)
        connection.create_function("pg_advisory_unlock", 1, lambda key: True)

    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "Session", sessions)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(workers, "Session", sessions)
    monkeypatch.setattr(workers, "engine", engine)

    def session_dependency():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session_dependency
    yield sessions
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(database):
    with TestClient(app) as test_client:
        yield test_client
