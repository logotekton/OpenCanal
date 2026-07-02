#!/usr/bin/env node
// opencanal-socket — "the pack's power outlet" (팩의 콘센트).
//
// A local stdio MCP server that any external workflow/tool (n8n, Claude Code, …) can plug into
// to (a) READ the owner's judgment pack (persona/knowledge/policies) and (b) FEED outcomes back,
// turning that external workflow into a sensor in the owner's circulatory system.
//
// Runs locally on the OWNER'S machine. The ocm_ token (OpenCrab credential) and the device token
// live only in ~/.opencanal/config.json — this process reads them but never forwards them anywhere
// except to opencrab.sh (ocm_) and the owner's own OpenCanal platform (device token).

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { nightQueueSchema } from "@opencanal/shared";
import { loadConfig, configPath } from "./config.js";
import { OpencrabClient } from "./opencrab.js";

const config = loadConfig();

/** Build an OpencrabClient from config, or null if the owner hasn't linked a pack. */
function getOpencrab(): OpencrabClient | null {
  if (!config.opencrab?.token) return null;
  return new OpencrabClient(config.opencrab.token, config.opencrab.mcpUrl);
}

const OCM_MISSING =
  `No OpenCrab pack is linked on this machine. The ocm_ token is missing from ${configPath}. ` +
  `Ask the owner to run the OpenCanal runner login and \`opencrab link\` first.`;

const server = new McpServer({ name: "opencanal-socket", version: "0.1.0" });

// ─────────────────────────────────────────────────────────────────────────────
// 1. pack_query — READ the owner's judgment/knowledge from their pack.
// ─────────────────────────────────────────────────────────────────────────────
server.registerTool(
  "pack_query",
  {
    description:
      "Query the pack owner's judgment and knowledge context before you make a decision on their behalf. " +
      "Use this whenever you are about to act, recommend, draft, approve, or reject something and want the " +
      "decision to reflect how THIS owner thinks — their preferences, style, prior decisions, red lines, and " +
      "domain knowledge. Ask a specific natural-language question (e.g. 'How does the owner decide whether to " +
      "accept a partnership request?' or 'What tone does the owner use when declining?'). Returns relevant " +
      "context retrieved from the owner's OpenCrab knowledge pack. Call this FIRST, then decide.",
    inputSchema: {
      question: z
        .string()
        .min(1)
        .describe("A specific natural-language question about the owner's judgment, preferences, or knowledge."),
      limit: z
        .number()
        .int()
        .positive()
        .optional()
        .describe("Max number of context items to retrieve (default 5)."),
    },
  },
  async ({ question, limit }) => {
    const client = getOpencrab();
    if (!client) return { content: [{ type: "text", text: OCM_MISSING }], isError: true };
    const context = await client.personaContext(question, limit ?? 5, config.opencrab?.workspaceId);
    return { content: [{ type: "text", text: context }] };
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// 2. report_outcome — FEED a real-world result back into the pack.
//    This is the tool that turns an external workflow into a SENSOR of the owner's
//    circulatory system: every decision + its real outcome trains future judgment.
// ─────────────────────────────────────────────────────────────────────────────
server.registerTool(
  "report_outcome",
  {
    description:
      "Report back the real-world outcome of a decision you made using the owner's pack, so the pack can LEARN from it. " +
      "This closes the loop: pack_query lets you read the owner's judgment; report_outcome writes the result back. " +
      "Call this AFTER a decision has been resolved by the owner or by reality — e.g. you drafted a reply and the " +
      "owner approved/sent it, you screened a request and it was accepted or rejected, an action you took was reverted. " +
      "Reporting outcomes (both approvals AND rejections) is what makes the external workflow a sensor in the owner's " +
      "circulatory system: each reported result becomes training signal for future judgment. Report generously.",
    inputSchema: {
      context: z.string().min(1).describe("What the judgment situation was (the decision you faced)."),
      decision: z.string().min(1).describe("The decision you made by referring to the owner's pack."),
      outcome: z
        .enum(["approved", "rejected"])
        .describe("The result from the owner or from reality: 'approved' (validated/accepted) or 'rejected' (overturned/declined)."),
      reason: z
        .string()
        .optional()
        .describe("Why it was approved or rejected — the correction signal. Especially valuable for rejections."),
    },
  },
  async ({ context, decision, outcome, reason }) => {
    const client = getOpencrab();
    if (!client) return { content: [{ type: "text", text: OCM_MISSING }], isError: true };

    const body = [
      `상황(판단 맥락): ${context}`,
      `내린 결정(팩을 참조함): ${decision}`,
      `결과(소유자/현실): ${outcome === "approved" ? "승인됨 (approved)" : "반려됨 (rejected)"}`,
      reason ? `사유: ${reason}` : null,
      "",
      "이 결과를 향후 판단에 반영하라.",
    ]
      .filter((l) => l !== null)
      .join("\n");

    try {
      const res = await client.ingestText(`외부 워크플로우 판단 결과 (${outcome})`, body, false);
      const where = res.workspaceId ? ` (workspace ${res.workspaceId})` : "";
      return {
        content: [
          {
            type: "text",
            text: `Outcome recorded into the owner's pack${where}. Future pack_query results will reflect this ${outcome} decision.`,
          },
        ],
      };
    } catch (err) {
      return {
        content: [
          {
            type: "text",
            text: `Failed to record outcome into the pack: ${err instanceof Error ? err.message : String(err)}`,
          },
        ],
        isError: true,
      };
    }
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// 3. pack_policies — READ the owner's standing policies + directives (the rules).
// ─────────────────────────────────────────────────────────────────────────────
server.registerTool(
  "pack_policies",
  {
    description:
      "Fetch the owner's standing judgment policies and standing directives — the explicit rules that govern how " +
      "the owner wants decisions made. Policies come in kinds: 'decision' (what is worth doing), 'red_flag' " +
      "(hard limits — never cross), 'style' (the owner's voice), and 'playbook' (how to execute). Use this to " +
      "load the owner's guardrails BEFORE acting on their behalf, and always respect red_flag policies. Complements " +
      "pack_query: pack_query gives fuzzy context, pack_policies gives the explicit rulebook. Takes no arguments.",
    inputSchema: {},
  },
  async () => {
    if (!config.deviceToken) {
      return {
        content: [
          {
            type: "text",
            text:
              `No device token found in ${configPath}. Policies are served by the owner's OpenCanal platform and ` +
              `require a logged-in runner. Ask the owner to run the OpenCanal runner login first.`,
          },
        ],
        isError: true,
      };
    }

    try {
      const res = await fetch(`${config.platformUrl}/api/night/queue`, {
        headers: { Authorization: `Bearer ${config.deviceToken}` },
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) {
        return {
          content: [{ type: "text", text: `Failed to fetch policies: HTTP ${res.status} from ${config.platformUrl}/api/night/queue` }],
          isError: true,
        };
      }
      const queue = nightQueueSchema.parse(await res.json());

      const kindLabel: Record<string, string> = {
        decision: "Decision policies (판단 기준)",
        red_flag: "Red flags (금지선 — never cross)",
        style: "Style (소유자다움)",
        playbook: "Playbooks (실행 요령)",
      };

      const sections: string[] = [];
      for (const kind of ["decision", "red_flag", "style", "playbook"] as const) {
        const items = queue.policies.filter((p) => p.kind === kind && p.active);
        if (items.length === 0) continue;
        sections.push(`## ${kindLabel[kind]}\n${items.map((p) => `- [P:${p.id}] ${p.text}`).join("\n")}`);
      }
      if (queue.directives.length > 0) {
        sections.push(`## Standing directives (상시 지시)\n${queue.directives.map((d) => `- ${d.content}`).join("\n")}`);
      }

      const owner = queue.ownerName ? ` — owner: ${queue.ownerName}` : "";
      const text =
        sections.length > 0
          ? `# ${queue.agent.displayName} (@${queue.agent.handle}) — judgment policies${owner}\n\n${sections.join("\n\n")}`
          : "No active policies or directives are defined yet.";

      return { content: [{ type: "text", text }] };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Failed to load policies: ${err instanceof Error ? err.message : String(err)}` }],
        isError: true,
      };
    }
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// stdio transport — all diagnostics go to stderr; stdout is the JSON-RPC channel.
// ─────────────────────────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("opencanal-socket ready (stdio). Tools: pack_query, report_outcome, pack_policies.");
}

main().catch((err) => {
  console.error("opencanal-socket failed to start:", err);
  process.exit(1);
});
