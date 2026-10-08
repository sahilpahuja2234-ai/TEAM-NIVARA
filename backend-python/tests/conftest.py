import os
import tempfile
from pathlib import Path

# Must happen before any `app` import: the engine is built at import time.
_TMP_DIR = tempfile.mkdtemp(prefix="nivara-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR, 'test.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # Entering the context runs the lifespan, i.e. create_all().
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session(client):
    with Session(engine) as s:
        yield s
        s.rollback()
        # Leave tables empty for the next test.
        for table in reversed(SQLModel.metadata.sorted_tables):
            s.exec(table.delete())
        s.commit()
