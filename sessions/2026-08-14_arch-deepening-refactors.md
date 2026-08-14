# Session: 2026-08-14_arch-deepening-refactors

- Date: 2026-08-14
- Session ID: (none provided)
- Agent: opencode (deepseek-v4-flash-free)
- Goal: Deepen 5 shallow modules (persistence, authorization, identity, scoped resources, schema mapping) per the improve-codebase-architecture skill; write RFCs in issues/ and implement.

## Spec
- Requirements / acceptance criteria
  - 5 RFC issue files in `issues/` following the skill's REFERENCE.md template
  - Implement all 5 phases; full test suite green after each phase
  - Testing policy per AGENTS.md: boundary tests for every change; replace, don't layer
  - Preserve existing HTTP behavior except the documented deliberate fixes (URL-lie 404, uniform 401, updated_at bump, atomic transactions)
- Scope and non-goals
  - No schema/migration changes; no new dependencies; no git history changes
  - Dead code removal: `utils/auth.create_refresh_token`, dead list schemas, orphaned `get_user_profile` stays (used by routes/auth import — verify)
- References: user request = "Explore the codebase, present deepening candidates" → "all" → "Accept all 5 recommendations" → "go"

## Work Done
(append per phase — see below)

## Files Changed
(append per phase)

## Tests
(append per phase)

## Notes
- TODO list per phase tracked in the session
- Risk: bulk UPDATE in remove_member bypasses updated_at listener (documented, matches current behavior)

## Phase 1 — Persistence seam (DONE)

- Created `persistence.py`: `get_or_404`, `first_or_404`, `first_or_raise`, `save`, `remove`, `flush_add`, `transaction(Session|Engine)` (nesting via `db._px_tx_depth`, refresh of `db.new` after outermost commit, rollback on ANY exception incl. HTTPException), class-level `before_flush` listener stamping `updated_at` on new/dirty rows, canonical model→404-detail map.
- Migrated services to it: `project_service` (create_project/transfer_project/update_project/delete_project/get_project), `task_service`, `member_service`, `comment_service`, `auth_service` (register/login/refresh/verify/forgot/reset/update_profile/change_password via `transaction`; `flush_add` for user-before-token; `first_or_raise` with preserved 401/400 semantics), `user_service.delete_user_cascade` (wrapped in `transaction`).
- Fixed `SelectOfScalar` import (removed in SQLAlchemy 2.0.50) → `Select[tuple[T]]`.
- Recreated broken `venv/` (pointed at another project's interpreter): `python3 -m venv venv` + `pip install -r requirements.txt pytest`.
- New `tests/test_persistence.py` (24 tests): get_or_404 (found/canonical detail/map/default/override), first_or_404, first_or_raise, save (create/update/commit=False), remove, flush_add, transaction (commit/rollback-on-HTTPException/nesting join/nested-failure-rolls-back/engine mode), updated_at listener (new rows, dirty bump, no breakage), project+member write via engine-mode transaction.
- Note: rule "no save()/remove() inside transaction blocks" proven by a test mistake (inner save() committed the outer unit) — tests now use db.add inside blocks.
- Suite: `pytest -q` → 177 passed (153 baseline + 24 new).

## Phase 2 — Authorization policy rewrite (DONE)

- Rewrote `services/permissions.py`: `Permission` enum (13 actions), `_Rule` dataclass matrix (min_role, subject rule, author_bypass, per-rule 404/400 details), `authorize()` → `ActorContext` (actor/project/subject, no re-fetch at call sites), `can()`, `pick_successor()` (moved from user_service). Check order: project 404 → author bypass → actor 404 "Project not found" → rank 403 → forbid_self 400 → subject 404 → subject-owner 400 → forbidden-role 400. Author bypass matches historical `_can_manage_comment` (author manages own comment without role OR membership).
- Migrated 17 call sites: project_service (get/update/delete/transfer via ctx), task_service (create uses task_create w/ assignee subject rule; get/update/delete), comment_service (`_comment_project_id` replaces `comment.task.project_id` lazy-load), member_service (add/role_update/remove), user_service (imports pick_successor). Deleted `get_membership_or_404`/`require_role`/`_ensure_assignee_is_member` usage where superseded (assignee check now the ASSIGNEE subject rule; kept helper only for update_task).
- New `tests/test_permissions_policy.py` (49 tests): full 13-permission min-role boundary matrix (allowed + below → 403), non-member/missing-project 404 hiding, assignee rule, comment author bypass (member author, removed author, non-author 403), member rules (owner-grant 400, missing target 404, target-owner 400), transfer rules (self 400, missing target 404), `can()`, `pick_successor` (highest role, earliest joined, owner excluded, empty).
- Suite: `pytest -q` → 226 passed (177 + 49).

## Phase 3 — Identity pipeline (DONE)

- Deleted `middleware/` (auth_middleware + package). `database.py`: no module-global engine; `make_engine(url, echo)` + `create_tables(engine)` + `get_session(request)` reading `request.app.state.engine`.
- `deps.py`: `authenticate(request, db) -> User|None` (Bearer → decode → db.get; None on any failure), `get_current_user` (401 "Not authenticated" + `WWW-Authenticate: Bearer`), `get_mailer`.
- `main.py`: lifespan sets `app.state.engine` (make_engine + owns_engine flag, disposed after), router-level `dependencies=[Depends(get_current_user)]` on project/task/comment/member routers.
- `services/emailer.py`: `Mailer` Protocol (`__call__(*, to, token_type, raw_token)`) + `resend_mailer` (stub print w/o RESEND_API_KEY). `auth_service.register_user`/`forgot_password` take `mailer=` kwarg; `send_email` deleted. Routes `/auth/register` + `/auth/forgot-password` inject `Depends(get_mailer)`; `/auth/logout` now requires auth (`Depends(get_current_user)`).
- Deleted dead `utils/auth.create_refresh_token`. Removed `middleware`/conftest double-patch; conftest sets `app.state.engine`, keeps `get_session` override, adds `FakeMailer` + `mailer` fixture.
- Replaced dead `test_auth.py:156-186` block with mailer-driven register→verify + forgot→reset lifecycle tests; fixed pre-existing URL typo `/projects/p/t/tasks/tid` → `/projects/p/tasks/tid` (middleware used to 401 before routing; malformed paths now 404 — documented delta).
- New tests: `tests/test_deps.py` (authenticate: valid/none/garbage/unknown-user/no-sub + 401 with Bearer challenge + deleted-user 401 + logout-requires-auth), `tests/test_security.py` (route audit: every non-public route resolves get_current_user; public routes reachable; unknown path → 404).
- Suite: `pytest -q` → 241 passed (226 + 15 net new).

## Phase 4 — Scoped resources (DONE)

- New `services/scope.py`: `ScopeHop`/`ScopePath`, `PROJECT_SCOPE`, `TASK_SCOPE`, `scoped_get` (authorize URL project → load row → walk hops proving each FK matches the URL anchor), `scoped_list` (authorize → task-scope proof when nested → filter on leaf FK; order_by/extra_filters/limit/offset).
- Deleted `get_tasks_for_project`, `get_task`, `get_comments_for_task`, `get_project_members`; list/get handlers now call `scoped_*` directly; mutation services take URL params (`update_task(project_id, task_id, ...)`, `delete_task(...)`, `update_comment(project_id, task_id, comment_id, ...)`, `delete_comment(...)`, `create_comment(project_id, task_id, ...)`) and resolve via `scoped_get` — the URL is authoritative, lies → 404.
- Removed `task_id` from `CreateCommentRequest` (was required in body, now purely from URL; extra body fields ignored → wire-compatible).
- Fixed scoped_list leaf-filter bug (used last hop's FK — ProjectTaskComment has no project_id; must use first hop).
- New tests: `tests/test_utils_scope.py` (17: happy paths, missing resource, URL-lies task-in-other-project / comment-under-wrong-task / task-under-wrong-project, non-member hiding, task-scope proof, ValueError on missing task_id, limit/offset), `TestUrlAuthority` in test_permissions.py (5 route-level URL-lie tests: GET/PUT via wrong project URL, comment via wrong task URL, comment via wrong project URL, cross-project double-membership case).
- Suite: `pytest -q` → 263 passed (241 + 22).

## Phase 5 — Schema mapping (DONE)

- New `schemas/base.py`: `APIResponse` (`ConfigDict(from_attributes=True)`), `Page[T]` (items/total/page/page_size/total_pages — the only envelope), `build_entity(model, body, *, exclude, **extras)` (extras win; unset body fields → model defaults).
- All response schemas extend `APIResponse`; deleted dead `TaskListResponse`, `CommentListResponse`, `MemberListResponse`, `PaginatedProjectResponse`; removed `CreateTaskRequest.project_id` and `CreateCommentRequest.task_id` (path-only; extra body fields ignored → wire-compatible).
- Routes now return `XResponse.model_validate(obj)` (all `_to_response` mappers and 3 hand-built UserResponse sites deleted); `list_projects` → `Page[ProjectResponse].model_validate(result)`.
- Typed services: `create_task(project_id, body, user_id, db)` via `build_entity`, `create_comment(project_id, task_id, body, user_id, db)`, `update_task`/`update_comment` take typed bodies (update-task whitelist/status coercion quirk preserved); removed dead `get_user_profile` + unused imports.
- New `tests/test_response_contract.py` (8 tests): schema↔column drift guard for all 5 response models, from_attributes wiring, dead-envelope absence, build_entity (merge/extras-win/exclude), Page nested ORM validation.
- Suite: `pytest -q` → 271 passed (263 + 8).

## Final

- Full suite: 271 passed. README updated (structure, auth deps, permissions matrix, persistence, URL authority, testing section, 271 tests).
- Deliberate behavior deltas (documented in README): single 401 body "Not authenticated" + WWW-Authenticate; unknown/malformed paths now 404 instead of 401; non-member requests hide existence uniformly ("Project not found"); URL lies → 404; `updated_at` now maintained by persistence listener.
- Work left uncommitted for user review (per AGENTS.md). Venv was broken (pointed at another project's interpreter) → recreated; requirements.txt + pytest installed.

## Fix: get_session request param leaked into OpenAPI (DONE)

- `/auth/register` (and every DB route) exposed a required query parameter named `request` in the OpenAPI — `get_session(request)` had an UNANNOTATED param, so FastAPI treated it as a query param. Tests never caught it because conftest overrides `get_session`.
- Fix: `get_session(request: Request)` in database.py.
- Regression tests in test_security.py: no route may expose a `request` query param; /auth/register has zero parameters + a RegisterRequest body only.
- Suite: 273 passed (271 + 2).
