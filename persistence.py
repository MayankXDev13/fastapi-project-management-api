"""Persistence toolkit: entity loading, failure mapping, and the unit-of-work boundary.

This module is the single home for:
- "fetch by id / by query, or fail" (get_or_404 / first_or_404 / first_or_raise)
- add+commit+refresh and delete+commit (save / remove)
- add+flush for rows whose PK is needed before commit (flush_add)
- the transaction boundary (transaction) — commits on success, rolls back on ANY
  exception (including HTTPException); nested calls join the outer unit.

`updated_at` is maintained by a class-level before_flush listener registered at
import time, giving every table model "onupdate" semantics without touching
models.py. Note: bulk Core UPDATE statements bypass the listener.

Rule: do not call save()/remove() inside a transaction block — their commit=True
default would split the unit. Use db.add / flush_add inside blocks instead.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Engine, Select, event
from sqlmodel import Session, SQLModel

from models import Project, ProjectMember, ProjectTask, ProjectTaskComment, User

T = TypeVar("T", bound=SQLModel)
M = TypeVar("M", bound=SQLModel)

_NOT_FOUND_DETAILS: dict[type[SQLModel], str] = {
    User: "User not found",
    Project: "Project not found",
    ProjectTask: "Task not found",
    ProjectTaskComment: "Comment not found",
    ProjectMember: "Project member not found",
}


def _default_detail(model: type[SQLModel]) -> str:
    return _NOT_FOUND_DETAILS.get(model, f"{model.__name__} not found")


def get_or_404(db: Session, model: type[M], pk: Any, detail: str | None = None) -> M:
    """Fetch by primary key; raise HTTP 404 (canonical message) if absent."""
    obj = db.get(model, pk)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or _default_detail(model),
        )
    return obj


def first_or_404(
    db: Session, stmt: Select[tuple[T]], detail: str | None = None
) -> T:
    """Execute a select; raise HTTP 404 if it returns no row."""
    obj = db.exec(stmt).first()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or "Resource not found",
        )
    return obj


def first_or_raise(
    db: Session, stmt: Select[tuple[T]], exc: HTTPException
) -> T:
    """Execute a select; raise the given exception (any status) if it returns no row."""
    obj = db.exec(stmt).first()
    if obj is None:
        raise exc
    return obj


def save(db: Session, obj: T, *, commit: bool = True, refresh: bool = True) -> T:
    """add + commit + refresh. Works for create AND update (add on a persistent
    object is a no-op). commit/refresh are opt-outs, not opt-ins."""
    db.add(obj)
    if commit:
        db.commit()
        if refresh:
            db.refresh(obj)
    return obj


def remove(db: Session, obj: T, *, commit: bool = True) -> None:
    """delete + commit. Cascades via FK ON DELETE."""
    db.delete(obj)
    if commit:
        db.commit()


def flush_add(db: Session, obj: T) -> T:
    """add + flush, returns obj with PK populated. Only needed where a child row
    references the parent's id (register_user, create_project)."""
    db.add(obj)
    db.flush()
    return obj


@contextmanager
def transaction(db_or_engine: Session | Engine) -> Iterator[Session]:
    """The single unit-of-work boundary.

    - Pass a Session (FastAPI DI): commits/rolls back on the caller's session,
      never closes it.
    - Pass an Engine (scripts, tests): opens its own session and closes it.
    - Nested calls join the outer transaction; only the outermost commits.
    """
    owns_session = isinstance(db_or_engine, Engine)
    db = Session(db_or_engine) if owns_session else db_or_engine

    if getattr(db, "_px_tx_depth", 0) > 0:  # nested: delegate to outer
        db._px_tx_depth += 1
        try:
            yield db
        finally:
            db._px_tx_depth -= 1
        return

    db._px_tx_depth = 1
    try:
        yield db
        added = list(db.new)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    else:
        for obj in added:  # reload DB-side defaults; replaces db.refresh()
            db.refresh(obj)
    finally:
        db._px_tx_depth = 0
        if owns_session:
            db.close()


@event.listens_for(Session, "before_flush")
def _stamp_updated_at(session, flush_context, instances) -> None:
    now = datetime.now(timezone.utc)
    for obj in (*session.new, *session.dirty):
        table = getattr(type(obj), "__table__", None)
        if table is not None and "updated_at" in table.columns:
            obj.updated_at = now