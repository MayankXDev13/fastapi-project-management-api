# Session: 2026-08-13_create-agent-workflow

- Date: 2026-08-13
- Session ID: 17638f8a-00ac-465c-aea8-ac2c96d644f5
- Agent: Muse Code powered by Meta Muse Spark
- Goal: Create AGENT.md with mandatory test and session-logging workflow for every project

## Spec

- User request: "write Agent.md file that have in every project write test cases and if the new session is create if agent done any work in code base i evry project creaet folder session/ and all spec and work done in this session any other informationa session-name.md"
- Requirements:
  1. Every project must write test cases for any change.
  2. If a new session is created and agent does any work in codebase, create folder `session/` (at repo root) if missing.
  3. For each such session, create `session/<session-name>.md` containing spec, work done, and any other session information.

## Work Done

- Created `AGENT.md` (5769 bytes) — defines General Principles, mandatory Testing Policy (§2), and Session Management Protocol (§3) including folder, naming, required sections, template, and lifecycle.
- Created `AGENTS.md` as identical copy for tooling that reads `AGENTS.md` (Muse Code, etc.).
- Created `session/` folder via `session/_template.md` template file.
- Created this session log `session/2026-08-13_create-agent-workflow.md`.

## Files Changed

- `AGENT.md` — created, workflow contract (testing + session logging)
- `AGENTS.md` — created, duplicate of AGENT.md for compatibility
- `session/_template.md` — created, reusable template for future sessions
- `session/2026-08-13_create-agent-workflow.md` — created, this log

## Tests

- No code logic to test. Verified files were written successfully via tool output (`wrote 5769 bytes`, `wrote 315 bytes`).
- Manual verification: `AGENT.md` and `AGENTS.md` are identical and contain §§ 1-5 and checklist.

## Notes

- Naming convention adopted: `session/YYYY-MM-DD_<slug>.md` (also supports `<session-id>_<slug>` prefix when ID available).
- Shell sandbox is currently unavailable (`bubblewrap` probe failed), so `ls`/`mkdir` via bash could not run; file creation via `muse.write_file` was used instead — parent dirs are auto-created.
- Future agents must read `AGENT.md` at session start and create/update their own `session/<session-name>.md` before first codebase write.
