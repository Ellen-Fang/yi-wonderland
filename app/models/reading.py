"""沿用原本 readings 資料表，既有 SQLite 資料不需搬移。"""
from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Reading(Base):
    __tablename__ = 'readings'
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)
