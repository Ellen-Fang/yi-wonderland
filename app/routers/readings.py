"""HTTP 端點只協調驗證、服務與資料儲存。"""
import asyncio
import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session
from app.crud import reading as crud
from app.db.session import get_db
from app.errors import ApiError
from app.schemas.reading import CreateReading, CreatedReadingResponse, DrawRequest, ReadingResponse
from app.services.interpreter import validate_interpretation
from app.services.tarot import SPREADS, draw_card, new_reading, public_reading, shuffle_deck

router = APIRouter(prefix='/api', tags=['塔羅占卜'])
Database = Annotated[Session, Depends(get_db)]


def access_token(authorization: Annotated[str | None, Header()] = None) -> str:
    return authorization[7:] if authorization and authorization.startswith('Bearer ') else ''


Token = Annotated[str, Depends(access_token)]


@router.get('/health')
async def health():
    return {'status': 'ok'}


@router.get('/spreads')
async def spreads():
    return {'spreads': SPREADS}


@router.post('/readings', status_code=201, response_model=CreatedReadingResponse)
async def create_reading(body: CreateReading, db: Database):
    reading = new_reading(body)
    token = secrets.token_urlsafe(32)
    crud.create(db, reading, token)
    return public_reading(reading) | {'accessToken': token}


@router.get('/readings/{reading_id}', response_model=ReadingResponse)
async def get_reading(reading_id: str, db: Database, token: Token):
    return public_reading(crud.get(db, reading_id, token))


@router.post('/readings/{reading_id}/draw', response_model=ReadingResponse)
async def draw(reading_id: str, body: DrawRequest, db: Database, token: Token):
    # 單一服務程序中不在讀取與保存之間 await，避免重複點擊造成覆寫。
    reading = crud.get(db, reading_id, token)
    draw_card(reading, body)
    crud.save(db, reading)
    return public_reading(reading)


@router.post('/readings/{reading_id}/shuffle', response_model=ReadingResponse)
async def shuffle(reading_id: str, db: Database, token: Token):
    reading = crud.get(db, reading_id, token)
    if reading['cards']:
        raise ApiError(409, 'SHUFFLE_LOCKED', '已經開始抽牌，不能重新洗牌。')
    reading['deck'] = shuffle_deck()
    crud.save(db, reading)
    return public_reading(reading)


@router.post('/readings/{reading_id}/interpretation', response_model=ReadingResponse)
async def interpretation(reading_id: str, request: Request, db: Database, token: Token):
    reading = crud.get(db, reading_id, token)
    if len(reading['cards']) != 3:
        raise ApiError(409, 'DRAW_REQUIRED', '請先依序抽完三張牌。')
    if reading['interpretation']:
        return public_reading(reading)
    jobs = request.app.state.interpretation_jobs
    if reading_id not in jobs:
        async def run():
            result = await request.app.state.interpreter(public_reading(reading))
            reading['interpretation'] = validate_interpretation(result, reading)
            # 任務使用自己的 session，請求中斷也不影響成功結果保存。
            with request.app.state.session_factory() as task_db:
                crud.save(task_db, reading)
            return public_reading(reading)

        task = asyncio.create_task(run())
        jobs[reading_id] = task

        def completed(job):
            jobs.pop(reading_id, None)
            if not job.cancelled():
                job.exception()  # 取得例外，避免無人等待時產生未處理任務警告。

        task.add_done_callback(completed)
    return await asyncio.shield(jobs[reading_id])
