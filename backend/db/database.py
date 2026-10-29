"""
backend/db/database.py
SQLAlchemy engine, session factory, and FastAPI dependency.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eyespy.db")

# StaticPool forces every thread onto one shared physical connection — that's
# only actually required for :memory: SQLite (a second connection would open
# a second, empty database). Applying it to the real file-based DB too meant
# the detection pipeline's background thread and an HTTP request thread could
# both be mid-commit on the *same* raw connection at once — harmless at low
# write volume, but once observations start writing often enough (multiple
# heuristics per frame), it surfaces as "cannot commit - no transaction is
# active". A real file lets each thread have its own connection instead,
# which is what SQLite is actually designed for.
_engine_kwargs = {"connect_args": {"check_same_thread": False}, "echo": False}
if ":memory:" in DATABASE_URL:
    _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and ensures it closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
