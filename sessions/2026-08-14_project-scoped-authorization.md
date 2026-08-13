# Session: 2026-08-14_project-scoped-authorization

- Date: 2026-08-14
- Session ID:
- Agent: opencode (deepseek-v4-flash-free)
- Goal: Add project-scoped authorization (roles) across the API, plus two adjacent bug fixes

## Spec
- Requirements (from /grilling session, user-approved):
  - Non-member → 404 (resource hiding) on project/task/comment/member reads
  - Member lacking role → 403
  - Matrix: owner = everything incl. transfer + delete project; admin = everything except transfer + delete; member = view, comment, create task; viewer = view only
  - Owner's membership row immutable by everyone except owner's own transfer
  - Transfer ownership via `POST /projects/{project_id}/transfer`; `owner_id` is single source of truth
  - `assigned_to` restricted to project members; cleared when member removed
  - Bug fixes: replace hand-rolled cascade deletes with FK `ondelete` + `PRAGMA foreign_keys=ON`; fix task unassign (None-skip bug)
  - `services/user_service.py::delete_user_cascade` helper (no endpoint): transfer owned projects to highest-role member (tie: earliest joined_at), else delete project
- Non-goals: migrations, superadmin, rate limiting, email changes, refresh-token reuse detection
- References: user /grilling session (2026-08-14)

## Work Done
- models.py: added `ondelete="CASCADE"` (members/tasks/comments/verification_tokens user FKs, task project FK) and `ondelete="SET NULL"` for `assigned_to`; added `passive_deletes` to relationships
- database.py: event listener to enable `PRAGMA foreign_keys=ON` on every SQLite connection
- services/permissions.py (new): `get_membership_or_404`, `require_role` helpers
- services/project_service.py: membership/role guards; removed hand-rolled cascade deletes; added `transfer_project`
- routes/project.py: wired guards; added `POST /projects/{project_id}/transfer`; schema `TransferProjectRequest`
- services/task_service.py: guards (create: owner/admin/member; update/delete: owner/admin); unassign fix (explicit None applied); `assigned_to` membership check
- services/comment_service.py: guards (create: not viewer; delete: owner/admin/author; membership for read/update)
- services/member_service.py: guards (mutations owner/admin); owner row immutable; removal clears `assigned_to`
- services/user_service.py (new): `delete_user_cascade` helper with fallback ownership rule
- README.md: documented permission matrix

## Files Changed
- `models.py` — FK cascade/SET NULL + passive_deletes
- `database.py` — PRAGMA foreign_keys listener
- `services/permissions.py` — new
- `services/project_service.py` — guards + transfer
- `services/task_service.py` — guards + bug fixes
- `services/comment_service.py` — guards
- `services/member_service.py` — guards
- `services/user_service.py` — new helper
- `routes/project.py` — guards + transfer endpoint
- `schemas/project.py` — TransferProjectRequest
- `tests/test_permissions.py` — new
- `.env.example` — new
- `README.md` — permission matrix

## Tests
- Added: `tests/test_permissions.py` (role matrix, transfer, owner immutability, 404 hiding, unassign fix, cascade deletes, delete_user_cascade units)
- Result: `pytest -q` — **153 passed** (101 existing + 52 new), 0 failures

## Notes
- TODOs: none
- Risks/Assumptions: SQLite FK enforcement requires the PRAGMA listener (added); middleware engine session benefits automatically (same engine object)
- Follow-ups: `.env.example` added (commit + push requested by user)