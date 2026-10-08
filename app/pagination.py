import base64
import json
import uuid
from datetime import datetime


def encode_cursor(clock_in_time: datetime, id: uuid.UUID) -> str:
    cursor = json.dumps(
        {
            "t": clock_in_time.isoformat(),
            "id": str(id)
        }
    )
    return base64.urlsafe_b64encode(cursor.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    cursor = base64.urlsafe_b64decode(cursor).decode()
    cursor = json.loads(cursor)
    return (datetime.fromisoformat(cursor["t"]), uuid.UUID(cursor["id"]))

