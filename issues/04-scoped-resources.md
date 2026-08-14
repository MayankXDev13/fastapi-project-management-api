# Issue: Deepen Scoped Resources — URL becomes the authority

## Problem

The "membership check then list" shape is copy-pasted 3× — `get_tasks_for_project` (`task_service.py:46-52`), `get_project_members` (`member_service.py:12-18`), `get_comments_for_task` (`comment_service.py:40-52`) — and the URL's scope params are decorative:

- `routes/task.py:72-79` `get_task_endpoint` accepts `project_id` but never uses it; membership is checked against `task.project_id`, not the URL's project
- All `routes/comment.py` handlers ignore `project_id`/`task_id` — a member of project B can hit `/projects/{A}/tasks/{task-in-B}/comments` and it resolves against B

The scoping invariant (URL project == resource's project, URL task == resource's task) exists nowhere as code. `_can_manage_comment`'s `comment.task.project_id` lazy-load is an N+1 trap.

## Proposed Interface

New module `services/scope.py`. Two entry points + two declarative path constants:

```python
# services/scope.py
ScopeHop = tuple[str, type[SQLModel], str]   # (fk attr on child, parent model, URL anchor name)
ScopePath = tuple[ScopeHop, ...]

PROJECT_SCOPE: ScopePath = (("project_id", Project, "project_id"),)
TASK_SCOPE: ScopePath = (("task_id", ProjectTask, "task_id"),
                         ("project_id", Project, "project_id"))

def scoped_get(db, model, resource_id, user_id, path, *, project_id, task_id=None) -> M:
    """Fetch one row and prove it lives under the URL's scope. 404 on any failure.
    Order: membership on URL project (404 hiding) → row exists (404) → each hop's
    FK matches its URL anchor (404). The URL is authoritative."""

def scoped_list(db, model, user_id, path, *, project_id, task_id=None,
                order_by=None, extra_filters=(), limit=None, offset=None) -> list[M]:
    """List rows under the URL scope. Task-scoped lists first prove the URL task
    belongs to the URL project, then filter by the leaf FK."""
```

404 semantics are uniform and indistinguishable (no existence oracle): non-member → `404 "Project not found"`; missing row or URL lied → `404 "<Model> not found"` (model-name map preserves today's strings: Task/Comment/Project member).

Usage (routes become thin; the four duplicated list/get service functions are deleted):

```python
# routes/task.py
tasks = scoped_list(db, ProjectTask, current_user.id, PROJECT_SCOPE, project_id=project_id)
task = scoped_get(db, ProjectTask, task_id, current_user.id, PROJECT_SCOPE, project_id=project_id)

# routes/comment.py — the URL can no longer lie
comments = scoped_list(db, ProjectTaskComment, current_user.id, TASK_SCOPE,
                       project_id=project_id, task_id=task_id)
comment = scoped_get(db, ProjectTaskComment, comment_id, current_user.id, TASK_SCOPE,
                     project_id=project_id, task_id=task_id)
```

Mutations stay in domain services but resolve through `scoped_get` and take the URL params (`update_task(project_id, task_id, ...)`, `update_comment(project_id, task_id, comment_id, ...)`); role gates afterwards use the URL `project_id`, proven equal to the resource's project.

## Dependency Strategy

**In-process** — pure logic over a `db: Session`. `scope.py` depends one-way on `services/permissions.py` (`authorize` with `Permission.project_view` for the membership gate) and on `models`; routes and services depend on `scope.py`. No DI changes; `permissions.py` stays the home of role gates.

## Testing Strategy

- **New boundary tests**: `tests/test_utils_scope.py` — happy path per scope depth; non-member → "Project not found"; missing resource → model detail; **URL-lie cases** (task in project B fetched via URL A; comment whose task_id mismatches the URL; task-scoped list under a foreign project) all → 404; missing required `task_id` → ValueError.
- **Route-level negative tests**: add URL-lie scenarios to `test_tasks.py`/`test_comments.py`/`test_members.py` asserting 404.
- **Old tests to delete**: direct coverage of the four deleted list/get functions; `_can_manage_comment` (its logic moves into `authorize` author-bypass in issue 02).
- **Behavior delta (intended)**: non-members asking for resources under a foreign project now get uniform "Project not found" instead of leaking the resource's existence via "Task not found" — worth a README note.

## Implementation Recommendations

- **What the module owns**: the containment chain (project → task → comment), membership-first ordering, scope validation, uniform 404s.
- **What it hides**: hop-walking via explicit FK columns (no lazy relationship loads), the membership gate, the model→detail message map.
- **What it exposes**: `scoped_get`, `scoped_list`, `PROJECT_SCOPE`, `TASK_SCOPE`.
- **Migration**: add `scope.py`; delete `get_tasks_for_project`/`get_project_members`/`get_comments_for_task`/`get_task`/`_can_manage_comment`; forward URL params in ~8 route handlers and 5 service functions. Query budget per endpoint is unchanged (membership + resource + list, all indexed). One accepted duplicate: mutations call `scoped_get` (membership) then `authorize` (membership again) — two indexed SELECTs, acceptable.
- **Future scopes** (e.g. attachments under tasks) are one more `ScopePath` constant — no code changes.