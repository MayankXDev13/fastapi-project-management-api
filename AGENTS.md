# Agent Guide — Project Workflow & Session Protocol

This file defines mandatory workflow rules for any AI agent (or human contributor acting via an agent) working in this repository. These rules apply to **every project** where this file is present.

---

## 1. General Principles

1.  **Read before you write.** Inspect existing code, tests, config, and docs before making changes.
2.  **Minimal, root-cause fixes.** Prefer the smallest correct fix at the root cause. No speculative refactors.
3.  **Follow existing conventions.** Match the project's architecture, naming, error handling, and code style.
4.  **No destructive actions.** Never rewrite git history, delete untracked user files, or `rm -rf` / `git clean` without explicit user approval.
5.  **Verify your work.** Run the project's own build/tests/linters where feasible before declaring done.

---

## 2. Testing Policy — Mandatory

> **Rule: Every code change must include tests. No exceptions.**

### 2.1 When to Write Tests

- New feature / endpoint / service / utility → tests for happy path + error/edge paths.
- Bug fix → reproduction test that fails before fix and passes after.
- Refactor → existing tests must still pass; add missing coverage if gap exists.
- Every project must maintain a `tests/` (or equivalent) suite.

### 2.2 Coverage Expectations

- Happy path, validation errors (400/422), auth errors (401/403), not-found (404), conflict (409), and boundary cases (empty, null, malformed, pagination limits).
- Business logic in `services/` and helpers in `utils/` must have unit tests.
- API routes must have integration tests via `TestClient` (or equivalent).

### 2.3 Where Tests Live

```
tests/
├── conftest.py          # fixtures: engine, db_session, client, helpers
├── test_<feature>.py    # one file per feature/domain
└── test_utils_*.py      # utils/helpers
```

- Keep project-owned verification tests separate from scratch probes.
- Scratch/debug scripts go to `/tmp` — never commit them, never add them to `tests/`.

### 2.4 Running Tests

```bash
pytest -v
pytest tests/test_<feature>.py -v
pytest -q --tb=short
```

- Run the relevant test file/package after each change; run the full suite when time allows.
- If a test fails on your change, fix your change — do not delete, skip, or narrow the test.

---

## 3. Session Management Protocol — Mandatory

> **Rule: If the agent does ANY work in the codebase during a session, it must create a session log. No session log = incomplete work.**

### 3.1 Folder

- Every project must have a folder at the repository root:

```
sessions/
```

- Create `sessions/` if it does not exist (plural — holds multiple session logs). Never delete or overwrite existing session files.
- Do **not** add `sessions/` to `.gitignore` — by default, session logs are committed for traceability. Only add it if the user explicitly requests it.

### 3.2 When to Create a Session File

- A new agent session/turn is started **and** the agent modifies, creates, or deletes any file in the codebase (code, config, docs, tests).
- Read-only investigations (no writes) do not require a session file, but may optionally log findings.

### 3.3 File Naming

```
sessions/<session-name>.md
```

- `<session-name>` = `YYYY-MM-DD_<slug>` or `<session-id>_<slug>`
- Slug: kebab-case short description, e.g. `add-jwt-refresh-rotation`, `fix-task-status-enum`, `setup-ci`.
- Examples:
  - `sessions/2026-08-13_add-project-pagination.md`
  - `sessions/2026-08-13_17638f8a-fix-auth-middleware.md`

- If the platform provides a session ID, prefix it for uniqueness.

### 3.4 What to Include in Each Session File

Every `sessions/<session-name>.md` must contain at minimum:

```markdown
# Session: <session-name>

- Date: YYYY-MM-DD
- Session ID: <id if available>
- Agent: <agent name/model>
- Goal: One-line objective

## Spec
- Requirements / acceptance criteria
- Scope and non-goals
- References: issue links, design docs, user request (verbatim if short)

## Work Done
- Summary of changes (bullet list)
- Files created/modified/deleted (with paths)
- Key decisions and rationale
- Commands run (tests, builds, migrations)

## Tests
- Tests added/modified
- Test results (pass/fail counts, observed output)

## Notes
- Remaining work / TODOs
- Risks, assumptions, follow-ups
- Any other session information (errors encountered, env details)
```

### 3.5 Template

Copy `sessions/_template.md` when creating a new session file (`sessions/_template.md` is the canonical template):

```markdown
# Session: YYYY-MM-DD_<slug>

- Date: YYYY-MM-DD
- Session ID: 
- Agent: 
- Goal: 

## Spec
- Requirements:
- Acceptance criteria:
- References:

## Work Done
- 

## Files Changed
- `path/to/file.py` — description

## Tests
- Added/Modified:
- Result: `pytest -q` — X passed

## Notes
- TODOs:
- Risks/Assumptions:
- Other info:

```

### 3.6 Lifecycle

1.  Session starts → read this `AGENTS.md` (also available as `AGENT.md` — both are kept identical).
2.  Before first write → ensure `sessions/` exists; create `sessions/<session-name>.md` from template.
3.  During work → append progress to the session file (do not defer to end).
4.  Session ends → finalize `Tests` and `Notes` sections; ensure file is saved.

---

## 4. Commit & Documentation

- Leave work uncommitted for user review unless user explicitly asks to commit/push.
- Update `README.md` / docs when behavior, API, or setup changes.
- Session files are documentation — keep them concise, factual, and grounded in observed output (no fabricated results).

---

## 5. Quick Checklist (Every Session That Writes Code)

- [ ] `sessions/` folder exists
- [ ] `sessions/<session-name>.md` created and filled (Spec + Work Done + Tests + Notes)
- [ ] Tests written for every change
- [ ] Tests executed and results recorded in session file
- [ ] No destructive git/file operations

---

*This file is the contract. If instructions conflict, this file takes precedence for workflow, testing, and session logging within this repository.*
