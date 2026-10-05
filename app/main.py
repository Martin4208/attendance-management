from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.routers import auth, members
from app.database import get_db

app = FastAPI()

app.include_router(auth.router)
app.include_router(members.router)

@app.get("/health")
def health(db: Session = Depends(get_db)):
    return db.execute(text("SELECT 1")).scalar()
