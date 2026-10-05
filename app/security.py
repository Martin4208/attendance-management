from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
import jwt
import uuid
from app.config import settings

pw_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return pw_hash.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    return pw_hash.verify(password, hashed_password)

def create_access_token(user_id: uuid.UUID) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": exp,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={"require": ["exp", "sub"]})
    try:
        return uuid.UUID(payload["sub"])
    except ValueError:
        raise jwt.InvalidTokenError("invalid subject")