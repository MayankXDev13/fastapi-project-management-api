# FastAPI Guide — Project Management API

A clean, production-ready **Project / Task Management REST API** (mini Jira / Asana) built with **FastAPI + SQLModel + SQLite + JWT**. Implements layered architecture, opaque refresh-token rotation, and full CRUD for projects, tasks, comments and members.

> Stack: `FastAPI 0.136` · `SQLModel 0.0.38` · `Pydantic 2` · `SQLite` · `PyJWT (HS256)` · `bcrypt` · `Resend` · `pytest`

---

## Features

- **Auth**: register → verify email → login (access + opaque refresh token) → refresh rotation → logout → forgot / reset password → `GET/PUT /auth/me` → `PUT /auth/change-password`
- **Projects**: create / list (paginated + search) / get / update / delete / transfer ownership. Owner auto-added as `owner` member.
- **Tasks**: CRUD under `/projects/{projectId}/tasks` with status `todo | in_progress | review | completed`
- **Comments**: CRUD under `/projects/{projectId}/tasks/{taskId}/comments`
- **Members**: list / add / update role (`owner|admin|member|viewer`) / remove under `/projects/{projectId}/members`
- **Authorization**: project-scoped roles enforced via a declarative permission matrix in `services/permissions.py` — non-members get `404`, members without the role get `403` (see [Permissions](#permissions))
- **URL authority**: every nested resource is validated against the URL (`services/scope.py`) — the path can't be lied to; mismatches are uniform `404`s
- **Auth**: FastAPI dependencies (`deps.authenticate`/`get_current_user`) + router-level guards — no middleware
- **Emails**: `services/emailer.py` `Mailer` seam (Resend + stub fallback `[EMAIL STUB]` when `RESEND_API_KEY` missing), injectable for tests
- **Tests**: 270+ pytest integration + unit tests with in-memory SQLite

---

## Project Structure

```
.
├── main.py                 # FastAPI app, lifespan (app.state.engine), routers
├── config.py               # env: DATABASE_URL, SECRET_KEY, JWT expiry, Resend
├── database.py             # make_engine + get_session(request) + create_tables
├── persistence.py          # save/remove/transaction/get_or_404 + updated_at listener
├── deps.py                 # authenticate + get_current_user (401) + get_mailer
├── models.py               # SQLModel tables + Enums
├── routes/                 # APIRouter thin layer → schemas ↔ services
│   ├── auth.py
│   ├── project.py
│   ├── task.py
│   ├── comment.py
│   └── member.py
├── schemas/                # Pydantic Request/Response models
│   ├── base.py             # APIResponse (from_attributes), Page[T], build_entity
│   ├── auth.py
│   ├── project.py
│   ├── task.py
│   ├── comment.py
│   └── member.py
├── services/               # Business logic + DB queries
│   ├── auth_service.py
│   ├── project_service.py
│   ├── task_service.py
│   ├── comment_service.py
│   ├── member_service.py
│   ├── permissions.py      # Permission enum + rule matrix + authorize/can
│   ├── scope.py            # scoped_get / scoped_list (URL = authority)
│   ├── emailer.py          # Mailer protocol + resend_mailer
│   └── user_service.py     # delete_user_cascade (ownership fallback helper)
├── utils/
│   └── auth.py             # bcrypt, JWT (access), sha256 token hashing
├── tests/                  # pytest suite (see Testing)
│   ├── conftest.py
│   ├── test_utils_auth.py
│   ├── test_auth.py
│   ├── test_projects.py
│   ├── test_tasks.py
│   ├── test_comments.py
│   ├── test_members.py
│   ├── test_permissions.py
│   └── test_security.py    # route audit: every protected route resolves get_current_user
├── requirements.txt
└── .env
```

**Data model** (`models.py`):

| Table | Fields |
|---|---|
| `users` | `id(uuid), email(unique), hash_password, is_email_verified, created_at, updated_at` |
| `verification_tokens` | `id, user_id(FK), token_hash(sha256), type(email_verification|password_reset|refresh_token), expires_at, used_at, device_name, ip_address` |
| `projects` | `id, name, description, owner_id(FK), status(active|archived|completed)` |
| `project_members` | `id, project_id(FK), user_id(FK), role(owner|admin|member|viewer), joined_at` — `UNIQUE(project_id,user_id)` |
| `project_tasks` | `id, project_id(FK), title, description, assigned_to(FK), created_by(FK), due_date, status(todo|in_progress|review|completed)` |
| `project_task_comments` | `id, task_id(FK), user_id(FK), comment` |

---

## Quick Start

### Prerequisites

- Python 3.10+
- `pip`

### 1. Clone & install

```bash
git clone <repo-url>
cd fastapi-guide
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Create `.env` in project root:

```env
DATABASE_URL="sqlite:///./fastapi_guide.db"
SECRET_KEY="change-me-to-a-long-random-string-in-production"
# Optional — if omitted, emails are stubbed to stdout
RESEND_API_KEY="re_xxx"
EMAIL_FROM="onboarding@resend.dev"
```

`config.py` defaults: `ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=30`, `REFRESH_TOKEN_EXPIRE_DAYS=7`.

### 3. Run

```bash
uvicorn main:app --reload
# or
fastapi dev main.py
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs` (Swagger), `http://localhost:8000/redoc`
- OpenAPI: `http://localhost:8000/openapi.json`

Tables are auto-created on startup via `create_tables()`.

---

## Authentication Flow

```
Register → VerificationToken(email_verification, 24h) → send_email
Login    → verify bcrypt → create_access_token({"sub": user.id}) + VerificationToken(refresh_token, 7d)
Refresh  → validate hash+type+unused+not_expired → mark used_at → issue new pair (rotation)
Logout   → mark refresh token used_at
Verify   → validate email_verification token → is_email_verified = true
Forgot   → if user exists: VerificationToken(password_reset, 1h) → send_email (always 200, no leak)
Reset    → validate password_reset token → hash_password(new)
```

**Authentication** (`deps.py`):

- Public routes: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/verify-email`, `/auth/forgot-password`, `/auth/reset-password`, `/docs`, `/openapi.json`, `/redoc`
- All other routes require `Authorization: Bearer <jwt>` — enforced per-route via `Depends(get_current_user)` (router-level on project/task/comment/member routers). `deps.authenticate` decodes the token and loads the `User`; `get_current_user` raises `401 {detail: "Not authenticated"}` with `WWW-Authenticate: Bearer` when it fails
- `tests/test_security.py` audits that every non-public route resolves `get_current_user` (a forgotten dependency fails the suite, not just the deploy)

**Token helpers** (`utils/auth.py`): `hash_password`/`verify_password` (bcrypt), `create_access_token`/`decode_token` (PyJWT), `generate_raw_token` (`token_hex(32)`), `hash_token` (`sha256`).

**Persistence** (`persistence.py`): `save`/`remove`/`flush_add`/`transaction` (commit-on-success, rollback on any exception, nesting joins the outer unit), `get_or_404`/`first_or_404`/`first_or_raise`. `updated_at` is stamped automatically on every insert/update by a `before_flush` listener — no service touches it.

---

## API Reference

Base URL: `http://localhost:8000`

### Auth — `/auth`

| Method | Path | Auth | Body | Response | Notes |
|---|---|---|---|---|---|
| POST | `/auth/register` | No | `{email, password}` | `201 UserResponse` | `409` if duplicate |
| POST | `/auth/login` | No | `{email, password}` | `200 TokenResponse` | `401` on bad creds |
| POST | `/auth/refresh` | No | `{refresh_token}` | `200 TokenResponse` | Rotation, `401` if reused/expired |
| POST | `/auth/logout` | No | `{refresh_token}` | `200 MessageResponse` | Idempotent |
| POST | `/auth/verify-email` | No | `{token}` | `200 MessageResponse` | `400` if invalid/expired/reused |
| POST | `/auth/forgot-password` | No | `{email}` | `200 MessageResponse` | Always 200 |
| POST | `/auth/reset-password` | No | `{token, new_password}` | `200 MessageResponse` | `400` if invalid |
| GET | `/auth/me` | Yes | — | `200 UserResponse` | `401` if no token |
| PUT | `/auth/me` | Yes | `{email?}` | `200 UserResponse` | Whitelist: `email` only |
| PUT | `/auth/change-password` | Yes | `{old_password, new_password}` | `200 MessageResponse` | `400` if old wrong |

`TokenResponse`: `{access_token, refresh_token, token_type: "bearer"}`

### Projects — `/projects`

| Method | Path | Auth | Query/Body | Response |
|---|---|---|---|---|
| POST | `/projects` | Yes | `{name, description?}` | `201 ProjectResponse` |
| GET | `/projects` | Yes | `?page=1&page_size=10&search=` | `200 PaginatedProjectResponse` |
| GET | `/projects/{projectId}` | Yes | — | `200 ProjectResponse` / `404` |
| PUT | `/projects/{projectId}` | Yes | `{name?, description?, status?}` | `200 ProjectResponse` |
| DELETE | `/projects/{projectId}` | Yes | — | `204` / `404` |
| POST | `/projects/{projectId}/transfer` | Yes | `{user_id}` | `200 ProjectResponse` / `400` self-or-owner-role / `403` |

List is scoped to `ProjectMember` where `user_id == current_user.id`, paginated (`ceil(total/page_size)`), `search` uses `ilike` on `name` and `description`.

`POST /projects/{projectId}/transfer` moves `owner_id` to an existing member, sets the new owner's role to `owner`, and demotes the old owner to `member`. It is the **only** way to change the owner role.

### Tasks — `/projects/{projectId}/tasks`

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/projects/{projectId}/tasks` | Yes | `{title, description?, assigned_to?, due_date?, status?}` | `201 TaskResponse` |
| GET | `/projects/{projectId}/tasks` | Yes | — | `200 TaskResponse[]` |
| GET | `/projects/{projectId}/tasks/{taskId}` | Yes | — | `200 TaskResponse` / `404` |
| PUT | `/projects/{projectId}/tasks/{taskId}` | Yes | `{title?, description?, assigned_to?, due_date?, status?}` | `200 TaskResponse` |
| DELETE | `/projects/{projectId}/tasks/{taskId}` | Yes | — | `200 MessageResponse` |

### Comments — `/projects/{projectId}/tasks/{taskId}/comments`

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/projects/{projectId}/tasks/{taskId}/comments` | Yes | `{comment}` | `201 CommentResponse` |
| GET | `/projects/{projectId}/tasks/{taskId}/comments` | Yes | — | `200 CommentResponse[]` |
| PUT | `/projects/{projectId}/tasks/{taskId}/comments/{commentId}` | Yes | `{comment}` | `200 CommentResponse` / `404` |
| DELETE | `/projects/{projectId}/tasks/{taskId}/comments/{commentId}` | Yes | — | `200 MessageResponse` |

### Members — `/projects/{projectId}/members`

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{projectId}/members` | Yes | — | `200 MemberResponse[]` |
| POST | `/projects/{projectId}/members` | Yes | `{user_id, role=member}` | `201 MemberResponse` / `409` duplicate |
| PUT | `/projects/{projectId}/members/{userId}` | Yes | `{new_role}` | `200 MemberResponse` / `404` |
| DELETE | `/projects/{projectId}/members/{userId}` | Yes | — | `200 MessageResponse` / `404` |

All protected routes return `401 {detail: "Not authenticated"}` when `Authorization` is missing/invalid. Unknown paths return `404` (auth no longer preempts routing).

## Permissions

Roles are **project-scoped** (stored on `project_members`). Identity comes from `deps.get_current_user`; authorization lives in `services/permissions.py` — a `Permission` enum backed by a rule matrix, exposed through `authorize()` (raises the canonical `404`/`403`/`400`) and `can()` (boolean).

Every task/comment/member read or write first resolves through `services/scope.py` (`scoped_get`/`scoped_list`): the row must live under the URL's project (and task), and the actor must be a member of the URL project — otherwise a uniform `404` (`"Project not found"` for non-members, hiding the resource's existence).

---

## Permissions

Roles are **project-scoped** (stored on `project_members`). Authentication lives in `deps.py` (identity); authorization lives in services via `services/permissions.py` (`authorize` over the `Permission` matrix).

| Action | owner | admin | member | viewer | non-member |
|---|---|---|---|---|---|
| View project / tasks / comments / members | ✅ | ✅ | ✅ | ✅ | `404` |
| Create task | ✅ | ✅ | ✅ | ❌ | `404` |
| Update / delete task | ✅ | ✅ | ❌ | ❌ | `404` |
| Post comment | ✅ | ✅ | ✅ | ❌ | `404` |
| Update / delete comment | ✅ | ✅ | + author | author only | `404` |
| Add member / change role / remove member | ✅ | ✅ | ❌ | ❌ | `404` |
| Update project | ✅ | ✅ | ❌ | ❌ | `404` |
| Transfer ownership | ✅ | ❌ | ❌ | ❌ | `404` |
| Delete project | ✅ | ❌ | ❌ | ❌ | `404` |

Rules:

- Non-member → `404` (hides the project's existence). Member without permission → `403`.
- The owner's membership row is immutable — only `POST /projects/{id}/transfer` (owner-only) can change it. Granting/removing the `owner` role through member endpoints returns `400`.
- `assigned_to` is restricted to project members; removing a member clears their task assignments.
- Task/comment/member endpoints require membership of the project in the URL path — `404` otherwise.

---

## Examples (curl)

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123"}'
# → {"access_token":"...","refresh_token":"...","token_type":"bearer"}

TOKEN="<access_token>"

# Create project
curl -X POST http://localhost:8000/projects \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"My Project","description":"demo"}'

# List with search + pagination
curl "http://localhost:8000/projects?search=My&page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN"

# Create task
PROJECT_ID="<project_id>"
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/tasks" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Setup CI","status":"todo"}'

# Refresh
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

---

## Testing

In-memory SQLite + real JWT via `TestClient`. No file DB is touched: the `client` fixture puts a `StaticPool` engine on `app.state.engine` and overrides `get_session`; a `FakeMailer` overrides `get_mailer` to capture raw verification tokens.

```bash
pip install pytest httpx pytest-asyncio   # if not already
pytest -v
pytest tests/test_auth.py -v
pytest -q --tb=short
```

**Suite** (`271 tests`):

| File | Coverage |
|---|---|
| `tests/test_utils_auth.py` | `hash_password`, `verify_password`, `create_access_token`/`decode_token`, expiry, tamper, `generate_raw_token`, `hash_token` |
| `tests/test_auth.py` | register (201/409/token), login (200/401), refresh (rotation/reuse/expired/invalid), logout, verify-email (success/reuse/invalid), forgot/reset (leak-safe, mailer lifecycle, success, invalid, reuse), `GET/PUT /auth/me`, `change-password`, auth guards (`Bearer` prefix, public paths) |
| `tests/test_projects.py` | create (success/no-desc/401/owner-member), list (empty/pagination/search by name+desc/case-insensitive/scoping/401), get/update/delete (success/404/partial/401) |
| `tests/test_tasks.py` | create (success/with assignee/401/422), list/get (empty/401/404), update/delete (success/partial/404/401) |
| `tests/test_comments.py` | create/list/update/delete (success/404/401/422) |
| `tests/test_members.py` | list (owner/401), add (success/default role/duplicate 409/roles), update role (success/404/401), remove (success/404/401) |
| `tests/test_permissions.py` | non-member `404` hiding, role matrix per endpoint (403/200), task assignment rules, unassign via `null`, cascade deletes, member-removal unassignment, transfer (success/roles/403/404/400), owner immutability, `delete_user_cascade` units, URL-authority lies |
| `tests/test_permissions_policy.py` | `authorize` unit matrix: min-role boundaries, 404 hiding, assignee rule, comment author bypass, member/transfer rules, `can()`, `pick_successor` |
| `tests/test_persistence.py` | `get_or_404`/`first_or_404`/`first_or_raise`, `save`/`remove`/`flush_add`, `transaction` (commit/rollback/nesting/engine mode), `updated_at` listener |
| `tests/test_utils_scope.py` | `scoped_get`/`scoped_list` happy paths, missing resources, URL-lie 404s, task-scope proof, limit/offset |
| `tests/test_deps.py` / `test_security.py` | `authenticate` units, 401 + `WWW-Authenticate`, logout requires auth, route audit |
| `tests/test_response_contract.py` | schema↔column drift guard, `from_attributes` wiring, `build_entity`, `Page` |

Fixtures (`tests/conftest.py`): `engine`, `db_session`, `client`, `mailer` (+ helpers `register_user`, `login_user`, `auth_headers`, `create_project`).

---

## Configuration Reference

| Var | Default | Description |
|---|---|---|
| `DATABASE_URL` | (required) | SQLAlchemy URL, e.g. `sqlite:///./fastapi_guide.db` |
| `SECRET_KEY` | `changeme-in-production` | HS256 signing key |
| `ALGORITHM` | `HS256` | JWT algo |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL (also verification token default) |
| `RESEND_API_KEY` | (none) | If missing, emails stub to stdout |
| `EMAIL_FROM` | `onboarding@resend.dev` | Resend `from` address |

---

## Deployment Notes

- Set a strong `SECRET_KEY` and use a managed DB (`postgresql://...`) in production — SQLite `check_same_thread=False` is dev-only.
- Put behind `uvicorn` with workers: `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4`
- The `on_event("startup")` hook is deprecated in newer FastAPI — migrate to `lifespan` for future versions.
- Consider adding `alembic` migrations instead of `create_all` for production schema evolution.
- `database.py` enables `PRAGMA foreign_keys=ON` per connection so FK `ON DELETE CASCADE` (members/tasks/comments) and `ON DELETE SET NULL` (`assigned_to`) are enforced by SQLite. `services/user_service.delete_user_cascade` transfers owned projects on user deletion (highest role, earliest `joined_at`; delete if no members) — wire it up when account deletion is added.

---

## License

MIT (or your choice) — add a `LICENSE` file if distributing.
