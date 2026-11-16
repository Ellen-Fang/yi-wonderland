"""SQLAlchemy 連線與每次請求使用的資料庫會話。"""
from pathlib import Path
from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models.reading import Base


def create_database(url: str):
    parsed = make_url(url)
    if parsed.drivername != 'sqlite':
        raise ValueError('本版僅支援 SQLite')
    memory = parsed.database in (None, '', ':memory:')
    if not memory:
        Path(parsed.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30},
                           **({'poolclass': StaticPool} if memory else {}))

    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, _):
        connection.execute('PRAGMA journal_mode=WAL')

    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session
