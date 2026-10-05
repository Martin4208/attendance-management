from sqlalchemy import create_engine
from app.config import settings
from sqlalchemy.orm import sessionmaker

engine = create_engine(settings.url, echo=True)

SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

