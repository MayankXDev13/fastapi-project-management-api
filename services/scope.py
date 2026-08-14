"""Scoped resources — the URL is the authority.

Every nested resource lives under exactly one containment chain
(project → task → comment). `scoped_get` / `scoped_list` prove that a row
belongs to the URL's scope before returning it; the URL cannot be lied to.

Semantics (uniform 404s, no existence oracle):
- non-member of the URL project         → 404 "Project not found"
- row does not exist                    → 404 "<Model> not found"
- row's FK contradicts the URL          → 404 with the anchor's model detail
- task-scoped queries first prove the   → the URL task exists AND belongs to
  URL task belongs to the URL project     the URL project, else 404
"""
from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException, status
from sqlmodel import SQLModel, Session, select

from models import Project, ProjectMember, ProjectTask, ProjectTaskComment
from persistence import _NOT_FOUND_DETAILS
from services.permissions import Permission, authorize

M = TypeVar("M", bound=SQLModel)

ScopeHop = tuple[str, type[SQLModel], str]  # (fk attr on child, parent model, URL anchor)
ScopePath = tuple[ScopeHop, ...]

PROJECT_SCOPE: ScopePath = (("project_id", Project, "project_id"),)
TASK_SCOPE: ScopePath = (
    ("task_id", ProjectTask, "task_id"),
    ("project_id", Project, "project_id"),
)


def _not_found(model: type[SQLModel]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_NOT_FOUND_DETAILS[model],
    )


def _walk_hops(
    db: Session, resource: M, path: ScopePath, anchors: dict[str, Any]
) -> None:
    current = resource
    for fk_attr, parent_model, anchor in path:
        if getattr(current, fk_attr) != anchors[anchor]:
            raise _not_found(parent_model)
        parent = db.get(parent_model, getattr(current, fk_attr))
        if parent is None:
            raise _not_found(parent_model)
        current = parent


def scoped_get(
    db: Session,
    model: type[M],
    resource_id: str,
    user_id: str,
    path: ScopePath,
    *,
    project_id: str,
    task_id: str | None = None,
) -> M:
    """Fetch one row and prove it lives under the URL's scope."""
    authorize(db, user_id, Permission.project_view, project_id)

    resource = db.get(model, resource_id)
    if resource is None:
        raise _not_found(model)

    anchors = {"project_id": project_id, "task_id": task_id}
    _walk_hops(db, resource, path, anchors)
    return resource


def scoped_list(
    db: Session,
    model: type[M],
    user_id: str,
    path: ScopePath,
    *,
    project_id: str,
    task_id: str | None = None,
    order_by=None,
    extra_filters: tuple = (),
    limit: int | None = None,
    offset: int | None = None,
) -> list[M]:
    """List rows under the URL's scope. Task-scoped lists first prove the URL
    task belongs to the URL project."""
    authorize(db, user_id, Permission.project_view, project_id)

    if len(path) > 1:
        if task_id is None:
            raise ValueError("task_id is required for a task-scoped list")
        task = db.get(ProjectTask, task_id)
        if task is None:
            raise _not_found(ProjectTask)
        if task.project_id != project_id:
            raise _not_found(Project)

    fk_attr = path[0][0]
    anchor = path[0][2]
    anchors = {"project_id": project_id, "task_id": task_id}
    query = select(model).where(getattr(model, fk_attr) == anchors[anchor])

    for extra in extra_filters:
        query = query.where(extra)
    if order_by is not None:
        query = query.order_by(order_by)
    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    return list(db.exec(query).all())