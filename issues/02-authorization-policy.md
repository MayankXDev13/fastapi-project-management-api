# Issue: Deepen Authorization — one permission matrix in `services/permissions.py`

## Problem

Authorization policy is scattered across 5 modules:

- `OWNER_OR_ADMIN` duplicated 4× (`project_service.py:12`, `task_service.py:10`, `member_service.py:9`, `comment_service.py:10`); `OWNER` (`project_service.py:11`), `CREATOR_ROLES` (`task_service.py:11`), `NON_VIEWER` (`comment_service.py:11`) are one-off names for the same ladder segments
- Role ranking + successor selection for project inheritance live in `user_service.py:5-19` (`_ROLE_RANK`, `_pick_successor`)
- Ownership invariants hand-rolled in `member_service.py:76-87, 113-117` (owner can't be demoted/removed) and the unassign-tasks side effect at `119-126`
- 17 call sites of the two primitives (`get_membership_or_404`, `require_role`) across 4 services

Changing the permission matrix (e.g. "member can edit tasks") means editing 4 service files plus their tests. The policy is not navigable as a single concept.

## Proposed Interface

Rewrite `services/permissions.py` (same path — old imports break loudly). Three authorization entry points + one ownership helper:

```python
class Permission(str, Enum):
    project_view / task_view / comment_view / member_view        # any member (404-hiding)
    project_update / project_delete / project_transfer           # admin / owner / owner
    task_create / task_update / task_delete                      # member / admin / admin
    comment_create / comment_update / comment_delete             # member / admin+author / admin+author
    member_add / member_role_update / member_remove              # admin + invariants

@dataclass(frozen=True)
class ActorContext:
    actor: ProjectMember
    project: Project
    subject: ProjectMember | None = None

def authorize(
    db: Session, actor_id: str, permission: Permission, project_id: str, *,
    subject_id: str | None = None, role: ProjectMemberRole | None = None,
) -> ActorContext:
    """One call: 'can actor do permission in project?'. Raises 404 (hiding) / 403 (rank) / 400 (invariants)."""

def can(db, actor_id, permission, project_id, *, subject_id=None, role=None) -> bool:
    """Non-raising predicate over the same code path — for unit tests and branch points."""

def remove_member(db, actor_id, project_id, target_user_id) -> ProjectMember:
    """authorize(member_remove) + the unassign-tasks side effect. Caller deletes + commits."""

def pick_successor(members: Sequence[ProjectMember]) -> ProjectMember | None:
    """Owner inheritance: highest non-owner rank, earliest joined_at wins. (from user_service)"""
```

Internals: one `_ROLE_RANK` ladder (viewer < member < admin < owner) + a 16-row `_Rule` table (`min_role`, subject rule, author-bypass, per-case 400/404 detail strings). `authorize` loads actor membership → 404 "Project not found" (hiding); loads project; author bypass (comment author may edit/delete); rank check → 403 "Insufficient permissions"; subject rules (assignee must be member → 404, target owner → 400, forbidden role → 400). `ActorContext` returns the resolved rows so callers stop re-querying.

Usage:

```python
# delete_project — was require_role + OWNER const + separate project fetch
ctx = authorize(db, user_id, Permission.project_delete, project_id)
remove(db, ctx.project)

# update_task — OWNER_OR_ADMIN + _ensure_assignee_is_member both disappear
authorize(db, user_id, Permission.task_update, task.project_id,
          subject_id=updated_data.get("assigned_to") or None)

# update_comment — author-or-admin falls out of author_bypass
authorize(db, user_id, Permission.comment_update, comment.task.project_id,
          subject_id=comment.user_id)
```

## Dependency Strategy

**In-process** — pure policy over a `db: Session`, no external services. The module raises `fastapi.HTTPException` directly (as all services already do), preserving every status code and detail string, so the existing TestClient suite is the migration safety net. Session is passed explicitly; no DI changes; routes untouched.

## Testing Strategy

- **New boundary tests**: matrix unit tests via `can()` — 16 permissions × (allowed / 403 / 404 / 400 where applicable), pure logic no HTTP; `pick_successor` tie-break and empty cases; `remove_member` side effect; `ActorContext` reuse.
- **Old tests to delete**: none wholesale — but the 4× duplicated-constant imports vanish and `_ensure_assignee_is_member`/`_can_manage_comment`/`_ROLE_RANK`/`_pick_successor` unit coverage is absorbed into the matrix tests.
- **Test environment needs**: existing `db_session` fixture.

## Implementation Recommendations

- **What the module owns**: the permission matrix, role ladder, 404-hiding, owner immutability, assignee-membership, comment author-bypass, successor selection, member-removal unassign.
- **What it hides**: all policy facts; services express intent as named permissions.
- **What it exposes**: `Permission` enum + `authorize`/`can`/`remove_member`/`pick_successor`.
- **Migration**: rewrite `permissions.py`; per service — delete role-set constants, map each call site to `authorize(...)`, delete `_ensure_assignee_is_member` and `_can_manage_comment`; `user_service` imports `pick_successor`; keep the 409 duplicate-member check and transfer's role mutations in their services (domain validation, not authorization). Blast radius is exactly the 4 service files + `user_service` (verified: nothing in routes/tests imports the old primitives).
- **Document**: min-rank is inclusive upward ("admin" means owner-or-admin); new permissions require enum member + rule row + test.
