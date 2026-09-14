# Project Notes for Claude

## MCP: tieum (틔움)

Tieum is the system of record for the patent generation and selection loop
(projects, tasks, patents, documents). It is registered in `.mcp.json` as a
streamable-HTTP MCP server.

- URL: `https://tieum.up.railway.app/api/mcp`
- Auth: `Authorization: Bearer ${TIEUM_API_KEY}` — the token is **not**
  committed because this repository is public. Set the `TIEUM_API_KEY`
  environment variable (in the Claude Code remote environment settings, or in
  the local shell) before starting a session so the server can connect.

### Usage rules

- Every tieum write tool requires an `author`. When acting for Ryan, use the
  email `youngwoo.yoon@superintel.kr` with agent name `claude-code`.
- All ids are UUIDs; use them exactly as given.
- Data is append-only: supersede instead of deleting, and record reasons when
  moving patents to rejected/dropped.
- Before working on something, claim the task (`claim_task`); record unrequested
  work afterwards via `create_tasks` with status `done`.
