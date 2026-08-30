"""
Tests for SqlAllowedRoleRepo.

Uses an in-memory SQLite database; no fakes needed.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from canvas_code_bot.data.db import Base
from canvas_code_bot.data.repositories import SqlAllowedRoleRepo

_NOW = datetime(2026, 8, 27, 12, 0, 0)


@pytest.fixture
def repo():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(engine)
    return SqlAllowedRoleRepo(sf)


def test_add_and_list(repo):
    repo.add(111, added_by=1, at=_NOW)
    roles = repo.list_all()
    assert len(roles) == 1
    assert roles[0].role_id == 111


def test_add_returns_allowed_role_with_id(repo):
    r = repo.add(222, added_by=1, at=_NOW)
    assert r.role_id == 222
    assert r.id != 0


def test_add_duplicate_is_idempotent(repo):
    repo.add(111, added_by=1, at=_NOW)
    repo.add(111, added_by=2, at=_NOW)
    assert len(repo.list_all()) == 1


def test_remove_existing(repo):
    repo.add(111, added_by=1, at=_NOW)
    repo.remove(111)
    assert repo.list_all() == []


def test_remove_nonexistent_is_safe(repo):
    repo.remove(999)  # must not raise


def test_has_any_true_when_one_matches(repo):
    repo.add(111, added_by=1, at=_NOW)
    assert repo.has_any({111, 222}) is True


def test_has_any_false_when_none_match(repo):
    repo.add(111, added_by=1, at=_NOW)
    assert repo.has_any({222, 333}) is False


def test_has_any_empty_set_is_false(repo):
    repo.add(111, added_by=1, at=_NOW)
    assert repo.has_any(set()) is False


def test_has_any_false_when_table_empty(repo):
    assert repo.has_any({111}) is False


def test_multiple_roles(repo):
    repo.add(100, added_by=1, at=_NOW)
    repo.add(200, added_by=1, at=_NOW)
    repo.add(300, added_by=1, at=_NOW)
    assert len(repo.list_all()) == 3


def test_remove_one_leaves_others(repo):
    repo.add(100, added_by=1, at=_NOW)
    repo.add(200, added_by=1, at=_NOW)
    repo.remove(100)
    remaining = {r.role_id for r in repo.list_all()}
    assert remaining == {200}
