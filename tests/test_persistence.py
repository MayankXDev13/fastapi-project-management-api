import pytest
from fastapi import HTTPException
from sqlalchemy import Engine
from sqlmodel import Session, select

from models import Project, ProjectMember, ProjectMemberRole, ProjectTask, User, VerificationToken
from persistence import (
    first_or_404,
    first_or_raise,
    flush_add,
    get_or_404,
    remove,
    save,
    transaction,
)


def _make_user(db: Session, email: str = "persist@example.com") -> User:
    return flush_add(db, User(email=email, hash_password="x"))


class TestGetOr404:
    def test_returns_object_when_found(self, db_session):
        user = _make_user(db_session)
        db_session.commit()
        assert get_or_404(db_session, User, user.id).id == user.id

    def test_missing_raises_canonical_404(self, db_session):
        with pytest.raises(HTTPException) as exc:
            get_or_404(db_session, Project, "nope")
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"

    def test_missing_task_uses_model_detail_map(self, db_session):
        with pytest.raises(HTTPException) as exc:
            get_or_404(db_session, ProjectTask, "nope")
        assert exc.value.detail == "Task not found"

    def test_unregistered_model_uses_default(self, db_session):
        with pytest.raises(HTTPException) as exc:
            get_or_404(db_session, VerificationToken, "nope")
        assert exc.value.detail == "VerificationToken not found"

    def test_detail_override_wins(self, db_session):
        with pytest.raises(HTTPException) as exc:
            get_or_404(db_session, Project, "nope", detail="Custom gone")
        assert exc.value.detail == "Custom gone"


class TestFirstOr404:
    def test_returns_first_row(self, db_session):
        _make_user(db_session)
        db_session.commit()
        user = first_or_404(db_session, select(User).where(User.email == "persist@example.com"))
        assert user.email == "persist@example.com"

    def test_missing_raises_404_with_default_detail(self, db_session):
        with pytest.raises(HTTPException) as exc:
            first_or_404(db_session, select(User).where(User.email == "absent@x.com"))
        assert exc.value.status_code == 404
        assert exc.value.detail == "Resource not found"

    def test_missing_raises_404_with_custom_detail(self, db_session):
        with pytest.raises(HTTPException) as exc:
            first_or_404(
                db_session,
                select(User).where(User.email == "absent@x.com"),
                detail="Nobody here",
            )
        assert exc.value.detail == "Nobody here"


class TestFirstOrRaise:
    def test_returns_row(self, db_session):
        _make_user(db_session)
        db_session.commit()
        user = first_or_raise(
            db_session,
            select(User).where(User.email == "persist@example.com"),
            HTTPException(status_code=418, detail="teapot"),
        )
        assert user.email == "persist@example.com"

    def test_missing_raises_given_exception(self, db_session):
        exc = HTTPException(status_code=418, detail="teapot")
        with pytest.raises(HTTPException) as raised:
            first_or_raise(
                db_session,
                select(User).where(User.email == "absent@x.com"),
                exc,
            )
        assert raised.value.status_code == 418
        assert raised.value.detail == "teapot"


class TestSave:
    def test_create_commits_and_refreshes(self, db_session):
        user = save(db_session, User(email="saved@x.com", hash_password="y"))
        assert user.id
        assert db_session.get(User, user.id) is not None

    def test_update_persists(self, db_session):
        user = save(db_session, User(email="saved@x.com", hash_password="y"))
        user.email = "changed@x.com"
        save(db_session, user)
        assert db_session.get(User, user.id).email == "changed@x.com"

    def test_commit_false_leaves_rollbackable(self, db_session):
        user = save(db_session, User(email="saved@x.com", hash_password="y"), commit=False)
        assert user.id
        db_session.rollback()
        assert db_session.get(User, user.id) is None


class TestRemove:
    def test_deletes_and_commits(self, db_session):
        user = save(db_session, User(email="saved@x.com", hash_password="y"))
        remove(db_session, user)
        assert db_session.get(User, user.id) is None


class TestFlushAdd:
    def test_populates_pk_without_commit(self, db_session):
        user = _make_user(db_session)
        assert user.id
        db_session.rollback()
        assert db_session.get(User, user.id) is None


class TestTransaction:
    def test_commits_on_success(self, db_session):
        with transaction(db_session):
            _make_user(db_session)
        assert db_session.get(
            User, db_session.exec(select(User)).one().id
        ).email == "persist@example.com"

    def test_rolls_back_on_http_exception(self, db_session):
        with pytest.raises(HTTPException):
            with transaction(db_session):
                _make_user(db_session)
                raise HTTPException(status_code=400, detail="boom")
        assert db_session.exec(select(User)).first() is None

    def test_nested_joins_outer_and_commits_once(self, db_session):
        with transaction(db_session):
            _make_user(db_session)
            with transaction(db_session):
                save(db_session, User(email="inner@x.com", hash_password="z"))
        assert len(db_session.exec(select(User)).all()) == 2

    def test_nested_failure_rolls_back_outer(self, db_session):
        with pytest.raises(HTTPException):
            with transaction(db_session):
                _make_user(db_session)
                with transaction(db_session):
                    db_session.add(User(email="inner@x.com", hash_password="z"))
                    raise HTTPException(status_code=400, detail="boom")
        assert db_session.exec(select(User)).first() is None

    def test_engine_mode_opens_own_session(self, engine):
        with transaction(engine) as db:
            db.add(User(email="engine@x.com", hash_password="y"))
        with Session(engine) as session:
            assert (
                session.exec(select(User).where(User.email == "engine@x.com")).first()
                is not None
            )


class TestUpdatedAtListener:
    def test_new_rows_get_updated_at(self, db_session):
        user = save(db_session, User(email="saved@x.com", hash_password="y"))
        assert user.updated_at is not None

    def test_dirty_rows_get_bumped(self, db_session):
        user = save(db_session, User(email="saved@x.com", hash_password="y"))
        before = user.updated_at
        user.email = "new@x.com"
        save(db_session, user)
        assert user.updated_at >= before

    def test_listener_does_not_break_explicit_updated_at(self, db_session):
        user = _make_user(db_session)
        project = save(
            db_session,
            Project(name="p", description="d", owner_id=user.id, status="active"),
        )
        assert project.updated_at is not None


class TestTransactionWithProject:
    def test_create_project_then_read_in_new_session(self, engine):
        with transaction(engine) as db:
            user = flush_add(db, User(email="own@x.com", hash_password="y"))
            project = Project(name="p", description="d", owner_id=user.id)
            db.add(project)
            db.flush()
            db.add(
                ProjectMember(
                    project_id=project.id, user_id=user.id, role=ProjectMemberRole.owner
                )
            )
        with Session(engine) as db:
            row = db.exec(select(Project)).one()
            assert row.name == "p"
            assert row.updated_at is not None