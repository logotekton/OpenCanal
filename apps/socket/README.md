# opencanal-socket — 팩의 콘센트 (the pack's power outlet)

A local **stdio MCP server** that lets any external workflow or tool — n8n, Claude Code, a cron
script, whatever — plug into the owner's OpenCanal judgment pack.

**판단은 읽고, 결과는 되돌린다.** Read the judgment, feed the outcome back.

- `pack_query` — read the owner's judgment/knowledge context before making a decision on their behalf.
- `report_outcome` — write the real-world result of that decision back into the pack, so it learns.
  This is what turns an external workflow into a **sensor in the owner's circulatory system**.
- `pack_policies` — read the owner's explicit rulebook (decision / red_flag / style / playbook + directives).

It runs **locally on the owner's machine**. The `ocm_` token (OpenCrab credential) and the device
token live only in `~/.opencanal/config.json` — this server reads them but never forwards them
anywhere except opencrab.sh (for `ocm_`) and the owner's own OpenCanal platform (for the device token).

## 전제 (prerequisites)

The socket reads `~/.opencanal/config.json`, which is written by the OpenCanal runner. Before using it:

1. Runner **login** completed (writes `deviceToken` + `platformUrl` — needed for `pack_policies`).
2. **`opencrab link`** completed (writes `opencrab.token` / `packId` / `workspaceId` — needed for
   `pack_query` and `report_outcome`).

If a token is missing, the relevant tool returns a clear error telling the owner what to run.

## 실행 (run)

```bash
pnpm --filter opencanal-socket build
node apps/socket/dist/index.js       # speaks MCP over stdio
```

During development:

```bash
pnpm --filter opencanal-socket dev
```

## Claude Code 등록 (register)

```bash
claude mcp add opencanal-socket -- node /absolute/path/to/OpenCanal/apps/socket/dist/index.js
```

## `.mcp.json` 예시

For any MCP client that reads a project `.mcp.json`:

```json
{
  "mcpServers": {
    "opencanal-socket": {
      "command": "node",
      "args": ["/absolute/path/to/OpenCanal/apps/socket/dist/index.js"]
    }
  }
}
```

(If installed globally via the `opencanal-socket` bin, `"command": "opencanal-socket"` with empty
`"args"` also works.)

## Tools

| Tool | Input | What it does |
| --- | --- | --- |
| `pack_query` | `{ question: string, limit?: number }` | Retrieves the owner's judgment/knowledge context (OpenCrab `opencrab_query`). Call it FIRST, then decide. |
| `report_outcome` | `{ context, decision, outcome: "approved"\|"rejected", reason? }` | Writes the resolved outcome back into the pack (`opencrab_ingest_text`, `create_pack:false`). Report approvals AND rejections. |
| `pack_policies` | `{}` | Fetches active policies + standing directives from the owner's platform (`GET /api/night/queue`). Respect `red_flag` policies. |

## 왜 콘센트인가

The runner is the owner's night worker. The socket is the wall outlet on the same circulatory
system: external tools plug in, draw the owner's judgment, and — crucially — return the outcome so
the judgment keeps improving. Every reported result is training signal.
