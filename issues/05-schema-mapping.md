# Issue: Deepen Schema Mapping — the response schema IS the mapper

## Problem

ORM→API mapping is hand-rolled in 5 places: `_to_response` in `routes/project.py:26-35`, `routes/task.py:24-36`, `routes/comment.py:23-31`, `routes/member.py:23-32`, plus `UserResponse` hand-constructed 3× in `routes/auth.py:40-46, 93-99, 111-117`. Response schemas mirror models 1:1 with **no** `model_validate`/`from_attributes` anywhere; services take untyped `dict[str, Any]` (`create_task`, `create_comment`); request bodies duplicate path params (`CreateTaskRequest.project_id` at `schemas/task.py:10`, `CreateCommentRequest.task_id` at `schemas/comment.py:5`) and the route silently overwrites the body value with the path value; 4 dead envelope schemas accumulate because nothing centralizes the mapping contract.

## Proposed Interface

One new module, two classes, one helper, one convention:

```python
# schemas/base.py
class APIResponse(BaseModel):
    """Base for every row-mapping response schema."""
    model_config = ConfigDict(from_attributes=True)

T = TypeVar("T")
class Page(BaseModel, Generic[T]):
    """The only pagination envelope. list[X] or Page[X] — no per-entity list schemas."""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

def build_entity(model: type[M], body: BaseModel, *, exclude: frozenset[str] = frozenset(), **extras: Any) -> M:
    """Merge path/actor extras (always win) with body fields (None → model defaults)."""
```

Conventions:
1. **Mapping**: every response schema extends `APIResponse`; routes return `Schema.model_validate(orm_obj)` (or a comprehension). The 4 `_to_response` mappers and 3 auth constructions are deleted. `hash_password` is never declared → excluded by declaration.
2. **Request binding**: create/update bodies contain **no field that is also a path param** — `project_id`/`task_id` deleted from `CreateTaskRequest`/`CreateCommentRequest` (wire-compatible: Pydantic ignores extra body fields, and the path was already authoritative). The path is the single source of truth by construction.
3. **Typed services**: `create_task(project_id: str, body: CreateTaskRequest, user_id: str, db)`, `update_task(project_id, task_id, body: UpdateTaskRequest, user_id, db)`, `create_comment(project_id, task_id, body: CreateCommentRequest, user_id, db)` — no `dict[str, Any]` crosses the route/service boundary. Update whitelists (`allowed_fields`) disappear — the typed schema IS the whitelist; `status` string-coercion disappears (Pydantic already parsed the enum).

Usage:

```python
# routes/task.py POST — dict assembly + overwrite hack + mapper, all gone
@router.post("", response_model=TaskResponse, status_code=201)
def create_task_endpoint(project_id: str, body: CreateTaskRequest,
                         current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_session)):
    return TaskResponse.model_validate(create_task(project_id, body, current_user.id, db))

# routes/task.py GET list — the response schema does the mapping
return [TaskResponse.model_validate(t) for t in
        scoped_list(db, ProjectTask, current_user.id, PROJECT_SCOPE, project_id=project_id)]

# routes/project.py — Page envelope replaces the hand-assembled dict
return Page[ProjectResponse].model_validate(
    get_all_projects(db=db, user_id=current_user.id, page=page, page_size=page_size, search=search))
```

## Dependency Strategy

**In-process** — pure Pydantic v2 data transformation. Standalone response schemas with `from_attributes=True`, NOT SQLModel inheritance (inheritance would leak `Relationship` attributes and `hash_password` into responses and drag lazy-loads into serialization). The schema declares the public shape; the ORM row supplies values at validation time. Services gain an import of the request schemas — the point of the change: the request schema is the service's input type. `schemas → models` (enums only) keeps the graph acyclic.

## Testing Strategy

- **New boundary tests**: `tests/test_response_contract.py` — the mirror invariant: every `APIResponse` field must exist as a column on its model (drift becomes a failing test, not a 500 at serialization time); `build_entity` extras-wins + None-defaults; `Page` validation. Existing HTTP tests pass unchanged (response JSON is byte-identical; redundant body fields are ignored).
- **Old tests to delete**: none — the mapper functions were only covered via HTTP integration, which now exercises the boundary convention directly.
- **Test environment needs**: none.

## Implementation Recommendations

- **What the module owns**: `from_attributes` wiring, field mapping, path/body/actor reconciliation, envelope construction, drift enforcement.
- **What it hides**: all field-by-field copying; schema/model drift is a test failure.
- **What it exposes**: `APIResponse`, `Page[T]`, `build_entity` — plus the two conventions.
- **Migration**: add `schemas/base.py`; swap response-schema bases; delete `project_id`/`task_id` body fields and the 4 dead list/envelope schemas; retype the 3 service functions; swap route bodies to `model_validate`; add the drift-guard test.
- **Boundary of the design**: nested responses need eager loading (relationship on a response schema must be loaded by the service — counts via subqueries, never mapper-side); projections/computed fields are new response classes with the service supplying attributes. None of these exist today; each has a documented, local escape hatch.
