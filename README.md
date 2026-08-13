# FastAPI Guide — Project Management API

A clean, production-ready **Project / Task Management REST API** (mini Jira / Asana) built with **FastAPI + SQLModel + SQLite + JWT**. Implements layered architecture, opaque refresh-token rotation, and full CRUD for projects, tasks, comments and members.

> Stack: `FastAPI 0.136` · `SQLModel 0.0.38` · `Pydantic 2` · `SQLite` · `PyJWT (HS256)` · `bcrypt` · `Resend` · `pytest`

---

## Features

- **Auth**: register → verify email → login (access + opaque refresh token) → refresh rotation → logout → forgot / reset password → `GET/PUT /auth/me` → `PUT /auth/change-password`
- **Projects**: create / list (paginated + search) / get / update / delete. Owner auto-added as `owner` member.
- **Tasks**: CRUD under `/projects/{projectId}/tasks` with status `todo | in_progress | review | completed`
- **Comments**: CRUD under `/projects/{projectId}/tasks/{taskId}/comments`
- **Members**: list / add / update role (`owner|admin|member|viewer`) / remove under `/projects/{projectId}/members`
- **Middleware**: `AuthMiddleware` (Bearer JWT) with public paths bypass
- **Emails**: via [Resend](https://resend.com) with stub fallback (`[EMAIL STUB]` when `RESEND_API_KEY` missing)
- **Tests**: 100+ pytest integration + unit tests with in-memory SQLite

---

## Project Structure

```
.
├── main.py                 # FastAPI app, middleware, routers, startup
├── config.py               # env: DATABASE_URL, SECRET_KEY, JWT expiry, Resend
├── database.py             # SQLModel engine + get_session + create_tables
├── deps.py                 # get_current_user (from request.state.user)
├── models.py               # SQLModel tables + Enums
├── middleware/
│   └── auth_middleware.py  # BaseHTTPMiddleware — validates Bearer JWT
├── routes/                 # APIRouter thin layer → schemas ↔ services
│   ├── auth.py
│   ├── project.py
│   ├── task.py
│   ├── comment.py
│   └── member.py
├── schemas/                # Pydantic Request/Response models
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
│   └── member_service.py
├── utils/
│   └── auth.py             # bcrypt, JWT (access), sha256 token hashing
├── tests/                  # pytest suite (see Testing)
│   ├── conftest.py
│   ├── test_utils_auth.py
│   ├── test_auth.py
│   ├── test_projects.py
│   ├── test_tasks.py
│   ├── test_comments.py
│   └── test_members.py
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

**Middleware** (`middleware/auth_middleware.py`):

- Public paths bypass auth: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/verify-email`, `/auth/forgot-password`, `/auth/reset-password`, `/docs`, `/openapi.json`, `/redoc`
- All other paths require `Authorization: Bearer <jwt>` → `decode_token()` → lookup `User` → `request.state.user`
- `deps.get_current_user` raises `401` if missing

**Token helpers** (`utils/auth.py`): `hash_password`/`verify_password` (bcrypt), `create_access_token`/`decode_token` (PyJWT), `generate_raw_token` (`token_hex(32)`), `hash_token` (`sha256`).

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

List is scoped to `ProjectMember` where `user_id == current_user.id`, paginated (`ceil(total/page_size)`), `search` uses `ilike` on `name` and `description`.

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

All non-public routes return `401 {detail: "Not authenticated"}` or `401 {detail: "Invalid or expired token"}` when `Authorization` is missing/invalid.

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

In-memory SQLite + real JWT via `TestClient`. No file DB is touched; `database.engine` and `middleware.auth_middleware.engine` are patched per test with `StaticPool`.

```bash
pip install pytest httpx pytest-asyncio   # if not already
pytest -v
pytest tests/test_auth.py -v
pytest -q --tb=short
```

**Suite** (`101 tests`):

| File | Coverage |
|---|---|
| `tests/test_utils_auth.py` | `hash_password`, `verify_password`, `create_access_token`/`decode_token`, expiry, tamper, `generate_raw_token`, `hash_token` |
| `tests/test_auth.py` | register (201/409/token), login (200/401), refresh (rotation/reuse/expired/invalid), logout, verify-email (success/reuse/invalid), forgot/reset (leak-safe, success, invalid, reuse), `GET/PUT /auth/me`, `change-password`, middleware (`Bearer` prefix, public paths) |
| `tests/test_projects.py` | create (success/no-desc/401/owner-member), list (empty/pagination/search by name+desc/case-insensitive/scoping/401), get/update/delete (success/404/partial/401) |
| `tests/test_tasks.py` | create (success/with assignee/401/422), list/get (empty/401/404), update/delete (success/partial/404/401) |
| `tests/test_comments.py` | create/list/update/delete (success/404/401/422) |
| `tests/test_members.py` | list (owner/401), add (success/default role/duplicate 409/roles), update role (success/404/401), remove (success/404/401) |

Fixtures (`tests/conftest.py`): `engine`, `db_session`, `client` (+ helpers `register_user`, `login_user`, `auth_headers`, `create_project`).

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
- `AuthMiddleware` currently does not enforce project-level authorization (any authenticated user can `GET/PUT/DELETE` any project/task). Add member/owner checks in services if needed.

---

## License

MIT (or your choice) — add a `LICENSE` file if distributing.
