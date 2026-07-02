// Socket config loader — reads ~/.opencanal/config.json (the runner's config).
// Read-only: this server never writes config. Secrets (deviceToken, ocm_ token)
// exist only on the user's machine and are never sent to the OpenCanal platform.
// Shape mirrors apps/runner/src/config.ts (read path only).

import { readFileSync, existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

export interface SocketConfig {
  platformUrl: string;
  gatewayUrl: string;
  deviceToken?: string;
  agentId?: string;
  handle?: string;
  opencrab?: {
    token: string; // ocm_ token — never leaves this machine
    packId: string;
    mcpUrl?: string;
    workspaceId?: string; // persona query scope
  };
  brain: {
    provider: "claude" | "codex";
  };
  limits: {
    concurrency: number;
    repliesPerHour: number;
  };
}

const CONFIG_DIR = join(homedir(), ".opencanal");
const CONFIG_PATH = join(CONFIG_DIR, "config.json");

const DEFAULTS: SocketConfig = {
  platformUrl: "http://localhost:3000",
  gatewayUrl: "ws://localhost:8787",
  brain: { provider: "claude" },
  limits: { concurrency: 3, repliesPerHour: 30 },
};

export function loadConfig(): SocketConfig {
  if (!existsSync(CONFIG_PATH)) return { ...DEFAULTS };
  try {
    const raw = JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
    return {
      ...DEFAULTS,
      ...raw,
      limits: { ...DEFAULTS.limits, ...raw.limits },
      brain: { ...DEFAULTS.brain, ...raw.brain },
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export const configPath = CONFIG_PATH;
