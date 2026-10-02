"""Run against a dedicated disposable DB: TEST_DATABASE_URL=... pytest tests/test_postgres.py."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Needs disposable PostgreSQL")
def test_advisory_lock_excludes_a_second_connection():
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    key = int.from_bytes(uuid.uuid4().bytes[:8], "big", signed=True)
    with engine.connect() as first, engine.connect() as second:
        assert first.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        assert not second.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        assert first.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key}).scalar()
        assert second.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        second.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    engine.dispose()
