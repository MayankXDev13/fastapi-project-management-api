# Issue: Deepen Persistence — one data-access toolkit for the whole app

## Problem

Persistence boilerplate is hand-rolled ~28 times across the 6 service modules:

- ~16 "fetch by id or 404" blocks (`db.get` + `if not obj: raise HTTPException(404)`): `project_service.py:35-40, 86-91, 108-113, 142-147`; `task_service.py:56-61, 69-74, 97-102`; `comment_service.py:25-30, 43-48, 58-63, 77-82`; `member_service.py:64-74, 102-112`; `auth_service.py:146-152, 250-255, 272-277`
- ~12 `db.add` → `db.commit` → `db.refresh` triples (e.g. `task_service.py:40-42`, `comment_service.py:34-36`, `member_service.py:49-51`)
- `updated_at = datetime.now(timezone.utc)` hand-set in 7 places — and *missed* in several (verify_email, refresh_token, logout_user mutate rows without stamping)
- No transaction boundary above a single service function: `register_user` (user + token + email), `transfer_project`, and `delete_user_cascade` are not atomic units
- Middleware opens its own `Session(engine)`, duplicating session lifecycle logic

These are all the same shape repeated; the interface at each call site is as large as the implementation. The integration risk is in the seams: inconsistent timestamping, no rollback path, easy-to-forget 404 branches.

## Proposed Interface

New module `persistence.py` (sibling of `database.py`). Plain functions taking `db: Session` — no repository class, no DI changes. Route and service signatures stay identical.

```python
# persistence.py
def get_or_404(db: Session, model: type[M], pk: str, detail: str | None = None) -> M: ...
def first_or_404(db: Session, stmt: SelectOfScalar[T], detail: str | None = None) -> T: ...
def first_or_raise(db: Session, stmt: SelectOfScalar[T], exc: HTTPException) -> T:
    """Non-404 failures (400/401 token checks) — caller supplies the exception."""
def save(db: Session, obj: T, *, commit: bool = True, refresh: bool = True) -> T:
    """add + commit + refresh; works for create AND update. commit/refresh are opt-outs."""
def remove(db: Session, obj: T, *, commit: bool = True) -> None: ...
def flush_add(db: Session, obj: T) -> T:
    """add + flush, returns obj with PK populated (child rows need parent id)."""
@contextmanager
def transaction(db_or_engine: Session | Engine) -> Iterator[Session]:
    """Unit of work. Commits on success, rolls back on ANY exception (incl. HTTPException).
    Accepts an Engine (opens+closes its own session) or a Session (never closes it).
    Nested calls join the outer unit; only the outermost commits."""
```

`updated_at` maintenance moves into a `before_flush` listener registered on the `Session` class at module import (covers every session, app and test, with zero conftest changes) — the listener is the mechanism that gives models `onupdate` semantics without touching `models.py`.

Usage example:

```python
# load-or-404 (was 5 lines)
task = get_or_404(db, ProjectTask, task_id, "Task not found")

# create (was add/commit/refresh)
return save(db, ProjectTask(**task_data))

# atomic multi-step (register_user: user + token commit together; email AFTER commit)
with transaction(db):
    user = flush_add(db, User(email=email, hash_password=hash_password(password)))
    raw_token = _create_verification_token(user.id, VerificationTokenType.email_verification, db)
send_email(to=email, subject="Verify your email", body=f"...token={raw_token}")
```

## Dependency Strategy

**Local-substitutable** (SQLite test DB already in place). `database.py` and FastAPI DI are untouched: routes keep `db: Session = Depends(get_session)`, services keep `db: Session` params. `transaction` additionally accepts an `Engine` so the middleware and scripts use the same unit-of-work semantics; tests run against the in-memory engine exactly as today.

## Testing Strategy

- **New boundary tests** (`tests/test_persistence.py`): `get_or_404`/`first_or_404` found/missing/custom detail; `first_or_raise` propagates the given exception instance; `save` commits + refreshes (row visible via a second session) and `save(commit=False)` does not commit; `remove`; `flush_add` populates PK; `transaction` commits all rows on success and rolls back everything when the block raises (assert zero rows via fresh session); `updated_at` bumps on dirty mutation and not on no-op; atomicity regression for `register_user` (monkeypatch token creation to raise → no rows persist).
- **Old tests to delete**: the ~16 inline 404 branches and ~12 commit/refresh triples are replaced by boundary coverage; per-service tests asserting 404 details stay (they pin the message map).
- **Test environment needs**: none beyond the existing `db_session` fixture.

## Implementation Recommendations

- **What the module owns**: entity loading (pk- and query-based), 404/400/401 failure mapping, commit/rollback discipline, `updated_at` maintenance, PK-after-flush.
- **What it hides**: session lifecycle decisions, timestamp policy, the flush dance, rollback on error.
- **What it exposes**: the 7 functions above — nothing else.
- **Migration**: add `persistence.py` + tests first; then per service: swap 404 blocks, wrap single-object mutations in `save`/`remove`, wrap multi-object ops in `transaction`, delete hand-set timestamps. Do not call `save()` inside a `transaction` block (its `commit=True` default would split the unit) — use `db.add`/`flush_add` there.
- **Known behavior deltas (bug fixes)**: `updated_at` now bumps on token/user mutations that previously skipped it; bulk `UPDATE` (member removal unassign) bypasses the listener — matches today, add `.values(updated_at=...)` explicitly if ever needed.
