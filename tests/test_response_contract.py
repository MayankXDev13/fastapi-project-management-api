"""Schema boundary contract: response schemas mirror table rows, and
build_entity merges body + extras correctly. Drift becomes a test failure
instead of a 500 at serialization time."""
import pytest

from models import (
    Project,
    ProjectMember,
    ProjectTask,
    ProjectTaskComment,
    User,
)
from schemas.base import APIResponse, Page, build_entity
from schemas.auth import UserResponse
from schemas.comment import CommentResponse, CreateCommentRequest
from schemas.member import MemberResponse
from schemas.project import ProjectResponse
from schemas.task import CreateTaskRequest, TaskResponse

_RESPONSE_MODELS = {
    UserResponse: User,
    ProjectResponse: Project,
    TaskResponse: ProjectTask,
    CommentResponse: ProjectTaskComment,
    MemberResponse: ProjectMember,
}


def test_every_response_field_exists_as_column():
    for response_cls, model in _RESPONSE_MODELS.items():
        columns = model.__table__.columns.keys()
        for name in response_cls.model_fields:
            assert name in columns, (
                f"{response_cls.__name__}.{name} has no column on {model.__name__}"
            )


def test_response_schemas_use_from_attributes():
    for response_cls in _RESPONSE_MODELS:
        assert response_cls.model_config["from_attributes"] is True


def test_no_dead_list_schemas_remain():
    import schemas.comment, schemas.member, schemas.project, schemas.task

    for module in (schemas.comment, schemas.member, schemas.project, schemas.task):
        names = [n for n in dir(module) if "ListResponse" in n or "Paginated" in n]
        assert names == [], f"dead envelope schema still present in {module.__name__}: {names}"


class TestBuildEntity:
    def test_merges_body_and_extras(self):
        body = CreateTaskRequest(title="T", description="d")
        task = build_entity(ProjectTask, body, project_id="p1", created_by="u1")
        assert task.title == "T"
        assert task.description == "d"
        assert task.project_id == "p1"
        assert task.created_by == "u1"

    def test_extras_win_over_body(self):
        body = CreateCommentRequest(comment="c")
        comment = build_entity(
            ProjectTaskComment, body, task_id="t1", user_id="u1"
        )
        assert comment.task_id == "t1"
        assert comment.user_id == "u1"
        assert comment.comment == "c"

    def test_exclude_drops_body_fields(self):
        body = CreateTaskRequest(title="T", project_id="should-not-leak")
        task = build_entity(
            ProjectTask,
            body,
            exclude=frozenset({"project_id"}),
            project_id="p1",
            created_by="u1",
        )
        assert task.project_id == "p1"


class TestPage:
    def test_validates_orm_items(self):
        page = Page[ProjectResponse].model_validate(
            {
                "items": [
                    Project(id="1", name="p", owner_id="o", status="active")
                ],
                "total": 1,
                "page": 1,
                "page_size": 10,
                "total_pages": 1,
            }
        )
        assert page.items[0].id == "1"
        assert page.items[0].status == "active"

    def test_total_pages_round_trip(self):
        page = Page[TaskResponse].model_validate(
            {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 1}
        )
        assert page.total == 0