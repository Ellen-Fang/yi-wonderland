"""FastAPI 入口：生命週期、CORS、錯誤格式、靜態牌面與路由。"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from app.config import CORS_ORIGINS, DATABASE_URL, ROOT
from app.db.session import create_database
from app.errors import ApiError
from app.routers.readings import router
from app.services.interpreter import interpret_reading


def create_app(database_url: str = DATABASE_URL, interpreter=interpret_reading) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        engine, factory = create_database(database_url)
        application.state.session_factory = factory
        application.state.interpreter = interpreter
        application.state.interpretation_jobs = {}
        try:
            yield
        finally:
            pending = list(application.state.interpretation_jobs.values())
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            engine.dispose()

    application = FastAPI(title='塔羅占卜 API', version='1.0.0', lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                               allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])

    def error_response(status, code, message):
        return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})

    @application.exception_handler(ApiError)
    async def api_error(_, error):
        return error_response(error.status, error.code, error.message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        return error_response(400, 'INVALID_INPUT', '請檢查輸入欄位、牌陣、字數與抽牌位置。')

    @application.exception_handler(HTTPException)
    async def http_error(_, error):
        return error_response(error.status_code, 'NOT_FOUND' if error.status_code == 404 else 'METHOD_NOT_ALLOWED', '找不到資源或此操作不受支援。')

    @application.exception_handler(Exception)
    async def unexpected_error(_, error):
        return error_response(500, 'INTERNAL_ERROR', '伺服器發生錯誤。')

    @application.middleware('http')
    async def request_limits(request: Request, call_next):
        if request.method == 'POST' and (request.url.path == '/api/readings' or request.url.path.endswith('/draw')):
            if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                return error_response(415, 'JSON_REQUIRED', '請使用 application/json。')
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16384:
                    return error_response(413, 'BODY_TOO_LARGE', '請求內容過大。')
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    application.include_router(router)
    application.mount('/cards', StaticFiles(directory=ROOT / 'public/cards'), name='cards')
    application.mount('/', StaticFiles(directory=ROOT / 'frontend', html=True), name='frontend')
    return application


app = create_app()
