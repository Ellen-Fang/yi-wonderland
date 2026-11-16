"""只負責資料讀寫，不處理 HTTP 或塔羅規則。"""
import hashlib
import json
import secrets
from sqlalchemy.orm import Session
from app.errors import ApiError
from app.models.reading import Reading


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(db: Session, reading: dict, token: str):
    db.add(Reading(id=reading['id'], token_hash=token_hash(token),
                   payload=json.dumps(reading, ensure_ascii=False)))
    db.commit()


def get(db: Session, reading_id: str, token: str) -> dict:
    row = db.get(Reading, reading_id)
    if row is None or not secrets.compare_digest(row.token_hash, token_hash(token)):
        raise ApiError(404, 'NOT_FOUND', '找不到占卜，或存取憑證不正確。')
    return json.loads(row.payload)


def save(db: Session, reading: dict):
    row = db.get(Reading, reading['id'])
    row.payload = json.dumps(reading, ensure_ascii=False)
    db.commit()
