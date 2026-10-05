import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import get_db
from app.main import app

test_url = settings.url.set(database=f"{settings.POSTGRES_DB}_test")
engine = create_engine(test_url)
TestingSessionLocal = sessionmaker(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        
        
@pytest.fixture(autouse=True)
def clean_db():
    if not engine.url.database.endswith("_test"):
        pytest.exit("Name of DB doesn't end with _test")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE attendance_records, audit_logs, memberships, tenants, users"))
    yield
    

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
