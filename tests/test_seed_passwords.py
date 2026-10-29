"""
tests/test_seed_passwords.py
The seed runs on any empty database, production included, and its default
passwords are published in the README. These cover the override that makes a
real deployment safe.
Run with: pytest tests/ -v
"""
import pytest
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import User
from backend.db.seed import seed_database

ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _fresh_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _password_of(db, username: str) -> str:
    return db.query(User).filter_by(username=username).one().password_hash


def test_defaults_are_used_when_nothing_is_configured():
    db = _fresh_db()
    seed_database(db)
    assert ctx.verify("admin123", _password_of(db, "admin"))
    db.close()


def test_env_override_replaces_the_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "a-strong-one")
    db = _fresh_db()
    seed_database(db)

    admin = _password_of(db, "admin")
    assert ctx.verify("a-strong-one", admin)
    # The published default must not survive alongside the override.
    assert not ctx.verify("admin123", admin)
    db.close()


def test_accounts_are_overridden_independently(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SEED_OPERATOR_PASSWORD", "operator-only")
    db = _fresh_db()
    seed_database(db)

    assert ctx.verify("operator-only", _password_of(db, "operator"))
    assert ctx.verify("admin123", _password_of(db, "admin"))
    db.close()


def test_default_use_is_announced(monkeypatch: pytest.MonkeyPatch, caplog):
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
    db = _fresh_db()
    with caplog.at_level("WARNING"):
        seed_database(db)

    warning = " ".join(r.getMessage() for r in caplog.records)
    assert "default passwords" in warning
    assert "admin" in warning
    db.close()


def test_seed_is_idempotent():
    db = _fresh_db()
    seed_database(db)
    before = db.query(User).count()
    seed_database(db)
    assert db.query(User).count() == before
    db.close()
