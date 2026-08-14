# Issue: Deepen Identity — delete the middleware, one authenticator + one session

## Problem

The identity pipeline is split and leaks its internals:

- **Two sessions per request**: `middleware/auth_middleware.py:56` opens its own `Session(engine)` to load the `User`, closes it, and stashes a *detached* object in `request.state.user`; the route's DI session then serves the rest of the request. Lazy loads on that user crash with `DetachedInstanceError`.
- **Engine is a module-global referenced by 2 modules** (`database.py:5`, `middleware/auth_middleware.py:6`) — `conftest.py:34-39` must patch both; any future importer silently breaks test isolation.
- **`deps.get_current_user` is a pure pass-through** — no token logic, no session logic, reads `request.state.user`.
- **The verification-token lifecycle has no test seam**: the raw token only ever reaches `send_email`'s body string, so `tests/test_auth.py:157-166` is an abandoned dead block that gives up and inserts tokens directly into the DB.

## Proposed Interface

Delete `middleware/auth_middleware.py`. Authentication becomes a FastAPI dependency; the engine moves to `app.state`; email becomes a swappable `Mailer`.

```python
# deps.py
def authenticate(request: Request, db: Session) -> User | None:
    """Bearer extraction + JWT decode + db.get(User, sub). Returns None on any failure.
    Pure function: no session lifecycle, no HTTP responses. Unit-testable without TestClient."""

def get_current_user(request: Request, db: Session = Depends(get_session)) -> User:
    """401 + WWW-Authenticate: Bearer unless authenticate() yields a User.
    Signature unchanged — all 22 route handlers compile as-is."""

def get_mailer() -> Mailer: ...   # returns resend_mailer

# database.py
def make_engine(url: str = DATABASE_URL, *, echo: bool = True) -> Engine: ...
def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
def create_tables(engine: Engine) -> None: ...
# module-global `engine` deleted

# services/emailer.py (new)
class Mailer(Protocol):
    def __call__(self, *, to: str, token_type: VerificationTokenType, raw_token: str) -> None: ...
def resend_mailer(*, to, token_type, raw_token) -> None: ...   # subject/body per type; stub print when no key
```

`main.py`: lifespan builds `app.state.engine = make_engine()`; `create_tables(app.state.engine)`; no `add_middleware`. Protected routers get `dependencies=[Depends(get_current_user)]` (project/task/comment/member); the three protected auth endpoints (`/auth/logout`, `/auth/me`, `/auth/change-password`) already have or gain the dependency. `auth_service.register_user`/`forgot_password` take a `mailer: Mailer = resend_mailer` kwarg; routes inject `mailer: Mailer = Depends(get_mailer)`.

Usage:

```python
# register → verify test — the dead block dies, real token end-to-end
def test_verify_email_full_lifecycle(client, mailer, db_session):
    client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
    raw = mailer.sent[0]["raw_token"]                     # ← the seam
    assert client.post("/auth/verify-email", json={"token": raw}).status_code == 200
    assert client.post("/auth/verify-email", json={"token": raw}).status_code == 400  # reuse fails
```

## Dependency Strategy

**Local-substitutable** (SQLite + TestClient). The engine is no longer importable — it lives at `app.state.engine`, set by the lifespan in production and by the test fixture in tests. `get_session` reads it per request, so exactly one session serves auth resolution and the endpoint. The conftest double-patch is deleted; the only seam is `app.state.engine` (+ `dependency_overrides[get_session]` where the session itself is swapped). Verification tokens become capturable because `raw_token` is a first-class structured argument to the mailer, not text inside a body string.

## Testing Strategy

- **New boundary tests**: `tests/test_deps.py` — `authenticate` with valid/missing/malformed token and unknown user; `get_current_user` 401 + header. `tests/test_security.py` — route-audit: every non-public route must resolve `get_current_user` (regression guard replacing the middleware's secure-by-default enforcement). `tests/test_auth.py` — replace the dead block with mailer-driven register→verify and forgot→reset lifecycle tests; keep direct-DB insertion for expired-token edge cases.
- **Old tests to delete**: the dead block at `test_auth.py:157-166`; the middleware engine patch in `conftest.py:34-48`; dead `utils/auth.create_refresh_token`.
- **Test environment needs**: `FakeMailer` fixture overriding `get_mailer`; `app.state.engine` set in the `client` fixture (lifespan skips creating its own when present).

## Implementation Recommendations

- **What the module owns**: token decode, identity resolution, 401 semantics, session acquisition, public-vs-protected routing, token delivery.
- **What it hides**: the JWT/`sub`/`db.get` pipeline and where the engine comes from.
- **What it exposes**: `authenticate`, `get_current_user`, `get_mailer`, `make_engine`/`get_session`.
- **Migration**: write `emailer.py` + rewrite `deps.py` + `database.py` + `main.py` + conftest; delete the middleware; wire the mailer kwarg through the two auth routes; add the audit test. All 22 handler signatures and every existing status-code assertion survive (verified: tests assert 401 status codes only, never the distinct bodies).
- **Behavior deltas (deliberate)**: 401 body collapses to one `{"detail": "Not authenticated"}`; unknown non-whitelisted paths now 404 instead of 401; a forgotten auth dependency is now caught by the audit test instead of the middleware.
- **Backstop option (not required)**: a DB-free JWT-only middleware shell can be layered later without reintroducing the engine coupling.
