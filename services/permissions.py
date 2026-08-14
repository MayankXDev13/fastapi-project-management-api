"""Authorization policy — the single home of "who may do what".

One entry point — `authorize` — turns (actor, permission, project, subject)
into an allowed `ActorContext` or an HTTP error with the canonical message:

- actor has no membership row        → 404 "Project not found"      (hides the project)
- project does not exist             → 404 "Project not found"
- actor's role is below the minimum  → 403 "Insufficient permissions"
- subject-related rules               → 404 / 400 with per-rule details
- comment author bypass               → allowed regardless of role or membership

`can` is the boolean variant. `pick_successor` resolves the next owner when a
user is deleted (highest role, earliest joined_at).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import Project, ProjectMember, ProjectMemberRole

_ROLE_RANK = {
    ProjectMemberRole.viewer: 0,
    ProjectMemberRole.member: 1,
    ProjectMemberRole.admin: 2,
    ProjectMemberRole.owner: 3,
}

_404_PROJECT = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
)
_403_PERMISSION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
)


class Permission(str, Enum):
    project_view = "project_view"
    task_create = "task_create"
    task_update = "task_update"
    task_delete = "task_delete"
    comment_create = "comment_create"
    comment_update = "comment_update"
    comment_delete = "comment_delete"
    member_add = "member_add"
    member_role_update = "member_role_update"
    member_remove = "member_remove"
    project_update = "project_update"
    project_delete = "project_delete"
    project_transfer = "project_transfer"


class _SubjectRule(str, Enum):
    none = "none"
    assignee = "assignee"                      # task create: assignee must be a member
    author = "author"                          # comment manage: author may bypass roles
    target_member = "target_member"            # member ops: the member being acted on
    new_member = "new_member"                  # member add: only role validation, no lookup


@dataclass(frozen=True)
class _Rule:
    min_role: ProjectMemberRole
    subject: _SubjectRule = _SubjectRule.none
    author_bypass: bool = False
    subject_not_found_detail: str | None = None
    subject_owner_detail: str | None = None
    forbid_self_detail: str | None = None
    forbidden_role: ProjectMemberRole | None = None
    forbidden_role_detail: str | None = None


_RULES: dict[Permission, _Rule] = {
    Permission.project_view: _Rule(ProjectMemberRole.viewer),
    Permission.task_create: _Rule(
        ProjectMemberRole.member,
        subject=_SubjectRule.assignee,
        subject_not_found_detail="User is not a project member",
    ),
    Permission.task_update: _Rule(ProjectMemberRole.admin),
    Permission.task_delete: _Rule(ProjectMemberRole.admin),
    Permission.comment_create: _Rule(ProjectMemberRole.member),
    Permission.comment_update: _Rule(
        ProjectMemberRole.admin,
        subject=_SubjectRule.author,
        author_bypass=True,
        subject_not_found_detail="Comment not found",
    ),
    Permission.comment_delete: _Rule(
        ProjectMemberRole.admin,
        subject=_SubjectRule.author,
        author_bypass=True,
        subject_not_found_detail="Comment not found",
    ),
    Permission.member_add: _Rule(
        ProjectMemberRole.admin,
        subject=_SubjectRule.new_member,
        forbidden_role=ProjectMemberRole.owner,
        forbidden_role_detail="Owner role can only be granted via project transfer",
    ),
    Permission.member_role_update: _Rule(
        ProjectMemberRole.admin,
        subject=_SubjectRule.target_member,
        subject_not_found_detail="Project member not found",
        subject_owner_detail="Owner role can only be changed via project transfer",
        forbidden_role=ProjectMemberRole.owner,
        forbidden_role_detail="Owner role can only be granted via project transfer",
    ),
    Permission.member_remove: _Rule(
        ProjectMemberRole.admin,
        subject=_SubjectRule.target_member,
        subject_not_found_detail="Project member not found",
        subject_owner_detail="Owner cannot be removed; transfer ownership first",
    ),
    Permission.project_update: _Rule(ProjectMemberRole.admin),
    Permission.project_delete: _Rule(ProjectMemberRole.owner),
    Permission.project_transfer: _Rule(
        ProjectMemberRole.owner,
        subject=_SubjectRule.target_member,
        subject_not_found_detail="User is not a project member",
        forbid_self_detail="User is already the project owner",
    ),
}


@dataclass
class ActorContext:
    """What authorize() proved. `subject` is the member row when a member was
    acted on; `project` is the loaded project (no extra query at call sites)."""

    actor: ProjectMember | None
    project: Project
    subject: ProjectMember | None = None


def _load_subject(
    db: Session, rule: _Rule, project_id: str, subject_id: str | None
) -> ProjectMember | None:
    if subject_id is None:
        return None
    return db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == subject_id,
        )
    ).first()


def authorize(
    db: Session,
    actor_id: str,
    permission: Permission,
    project_id: str,
    *,
    subject_id: str | None = None,
    role: ProjectMemberRole | str | None = None,
) -> ActorContext:
    rule = _RULES[permission]

    project = db.get(Project, project_id)
    if project is None:
        raise _404_PROJECT

    # Author bypass: a comment's author may manage it without any role or
    # membership (matches the historical _can_manage_comment early return).
    if rule.author_bypass:
        subject_row = _load_subject(db, rule, project_id, subject_id)
        if subject_id is not None and subject_id == actor_id:
            return ActorContext(actor=None, project=project, subject=subject_row)
    else:
        subject_row = None

    actor = _load_subject(db, rule, project_id, actor_id)
    if actor is None:
        raise _404_PROJECT

    if _ROLE_RANK[actor.role] < _ROLE_RANK[rule.min_role]:
        raise _403_PERMISSION

    if rule.forbid_self_detail and subject_id is not None and subject_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=rule.forbid_self_detail,
        )

    if rule.subject == _SubjectRule.assignee:
        if subject_id is not None and _load_subject(db, rule, project_id, subject_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=rule.subject_not_found_detail,
            )
        return ActorContext(actor=actor, project=project)

    if rule.subject == _SubjectRule.new_member:
        if rule.forbidden_role is not None and role is not None:
            if ProjectMemberRole(role) == rule.forbidden_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=rule.forbidden_role_detail,
                )
        return ActorContext(actor=actor, project=project)

    if rule.subject == _SubjectRule.author:
        if subject_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=rule.subject_not_found_detail,
            )
        return ActorContext(actor=actor, project=project, subject=subject_row)

    if rule.subject == _SubjectRule.target_member:
        if subject_id is None:
            return ActorContext(actor=actor, project=project)
        subject_row = _load_subject(db, rule, project_id, subject_id)
        if subject_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=rule.subject_not_found_detail,
            )
        if subject_row.role == ProjectMemberRole.owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=rule.subject_owner_detail,
            )
        if rule.forbidden_role is not None and role is not None:
            if ProjectMemberRole(role) == rule.forbidden_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=rule.forbidden_role_detail,
                )
        return ActorContext(actor=actor, project=project, subject=subject_row)

    return ActorContext(actor=actor, project=project)


def can(
    db: Session,
    actor_id: str,
    permission: Permission,
    project_id: str,
    *,
    subject_id: str | None = None,
    role: ProjectMemberRole | str | None = None,
) -> bool:
    """Boolean variant of authorize — no exceptions escape."""
    try:
        authorize(
            db,
            actor_id,
            permission,
            project_id,
            subject_id=subject_id,
            role=role,
        )
        return True
    except HTTPException:
        return False


def pick_successor(members: list[ProjectMember]) -> ProjectMember | None:
    """Next owner candidate for a deleted user: highest role, earliest joined_at."""
    candidates = [m for m in members if m.role != ProjectMemberRole.owner]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda m: (_ROLE_RANK[m.role], -m.joined_at.timestamp()),
    )