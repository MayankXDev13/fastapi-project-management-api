import os
import sys
import warnings

# Suppress noisy warnings that are already fixed in code but still emitted by deps
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*StarletteDeprecationWarning.*")
warnings.filterwarnings("ignore", message=".*Using `httpx`.*")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

from database import register_foreign_keys_listener


@pytest.fixture()
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    register_foreign_keys_listener(test_engine)
    SQLModel.metadata.create_all(test_engine)

    yield test_engine

    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(engine):
    with Session(engine) as session:
        yield session


class FakeMailer:
    """Captures raw verification tokens delivered via the get_mailer seam."""

    def __init__(self):
        self.sent: list[dict] = []

    def __call__(self, *, to, token_type, raw_token):
        self.sent.append(
            {"to": to, "token_type": token_type, "raw_token": raw_token}
        )


@pytest.fixture()
def client(engine):
    """TestClient with a test engine on app.state + overridden get_session."""
    from main import app
    from database import get_session

    app.state.engine = engine

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session_override

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def mailer(client):
    """Installs a FakeMailer as the get_mailer dependency; yields the fake."""
    from main import app
    from deps import get_mailer

    fake = FakeMailer()
    app.dependency_overrides[get_mailer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_mailer, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register_user(client: TestClient, email: str = "alice@example.com", password: str = "secret123"):
    """Register via API, returns response json."""
    return client.post("/auth/register", json={"email": email, "password": password})


def login_user(client: TestClient, email: str = "alice@example.com", password: str = "secret123"):
    """Login via API, returns TokenResponse dict."""
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(client: TestClient, email: str = "alice@example.com", password: str = "secret123"):
    """Register + login and return Authorization headers + tokens."""
    register_user(client, email, password)
    tokens = login_user(client, email, password)
    return {
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        "tokens": tokens,
    }


def create_project(client: TestClient, headers: dict, name: str = "Test Project", description: str = "desc"):
    resp = client.post("/projects", json={"name": name, "description": description}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
