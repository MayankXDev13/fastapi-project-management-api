from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)




class VerificationTokenType(str, Enum):
    email_verification = "email_verification"
    password_reset = "password_reset"
    refresh_token = "refresh_token"


class ProjectStatus(str, Enum):
    active = "active"
    archived = "archived"
    completed = "completed"


class ProjectMemberRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    completed = "completed"




class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)

    email: str = Field(unique=True, index=True)
    hash_password: str

    is_email_verified: bool = False

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    verification_tokens: List["VerificationToken"] = Relationship(
        sa_relationship_kwargs={"overlaps": "user", "passive_deletes": True}
    )
    owned_projects: List["Project"] = Relationship(
        sa_relationship_kwargs={"overlaps": "owner", "passive_deletes": True}
    )




class VerificationToken(SQLModel, table=True):
    __tablename__ = "verification_tokens"

    id: str = Field(default_factory=_uuid, primary_key=True)

    user_id: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True
    )

    token_hash: str

    type: VerificationTokenType

    expires_at: datetime
    used_at: Optional[datetime] = None

   
    device_name: Optional[str] = None
    ip_address: Optional[str] = None

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    user: Optional["User"] = Relationship(
        sa_relationship_kwargs={"overlaps": "verification_tokens"}
    )




class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=_uuid, primary_key=True)

    name: str
    description: Optional[str] = None

    owner_id: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True
    )

    status: ProjectStatus = Field(
        default=ProjectStatus.active
    )

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    owner: Optional["User"] = Relationship(
        sa_relationship_kwargs={"overlaps": "owned_projects", "passive_deletes": True}
    )
    members: List["ProjectMember"] = Relationship(
        sa_relationship_kwargs={"overlaps": "project", "passive_deletes": True}
    )
    tasks: List["ProjectTask"] = Relationship(
        sa_relationship_kwargs={"overlaps": "project", "passive_deletes": True}
    )




class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_members"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_member"
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)

    project_id: str = Field(
        foreign_key="projects.id",
        ondelete="CASCADE",
        index=True
    )

    user_id: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True
    )

    role: ProjectMemberRole = Field(
        default=ProjectMemberRole.member
    )

    joined_at: datetime = Field(default_factory=_now)

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    project: Optional["Project"] = Relationship(
        sa_relationship_kwargs={"overlaps": "members", "passive_deletes": True}
    )
    user: Optional["User"] = Relationship()




class ProjectTask(SQLModel, table=True):
    __tablename__ = "project_tasks"

    id: str = Field(default_factory=_uuid, primary_key=True)

    project_id: str = Field(
        foreign_key="projects.id",
        ondelete="CASCADE",
        index=True
    )

    title: str

    description: Optional[str] = None

    assigned_to: Optional[str] = Field(
        foreign_key="users.id",
        ondelete="SET NULL",
        default=None,
        index=True
    )

    created_by: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True
    )

    due_date: Optional[datetime] = None

    status: TaskStatus = Field(
        default=TaskStatus.todo
    )

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    project: Optional["Project"] = Relationship(
        sa_relationship_kwargs={"overlaps": "tasks", "passive_deletes": True}
    )
    comments: List["ProjectTaskComment"] = Relationship(
        sa_relationship_kwargs={"overlaps": "task", "passive_deletes": True}
    )


class ProjectTaskComment(SQLModel, table=True):
    __tablename__ = "project_task_comments"

    id: str = Field(default_factory=_uuid, primary_key=True)

    task_id: str = Field(
        foreign_key="project_tasks.id",
        ondelete="CASCADE",
        index=True
    )

    user_id: str = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True
    )

    comment: str

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    task: Optional["ProjectTask"] = Relationship(
        sa_relationship_kwargs={"overlaps": "comments", "passive_deletes": True}
    )
    user: Optional["User"] = Relationship()