# Rules for Codex (implementer)

- Read `docs/ARCHITECTURE.md` first. It is the binding contract (API paths, JSON shapes, error codes, DB schema, roles, concurrency design, Socket.IO events, i18n). Do NOT change requirements, architecture, endpoints, or `db/schema.sql`. If something in the contract seems wrong, implement it as specified and note the issue in your final message.
- Write complete, working files in place. No pseudo-code, no TODO stubs, no snippets.
- Only touch the files listed in your task. Other files may be edited concurrently by another agent.
- Python 3.12 venv at `.venv/` (dependencies already installed from `requirements.txt`; do not add new dependencies unless the task allows).
- PostgreSQL: `localhost:5434` (db `graduation`, test db `graduation_test`, user/pass `grad/grad`). Redis: `localhost:6380`. Both are running in docker.
- Core business rules MUST be enforced in the backend (state machine, conditional UPDATEs, locks), never only in the frontend.
- Do not run `git` commands that modify history (no commit/reset/checkout). The architect manages git.
