// Runner config — %USERPROFILE%\.opencanal\config.json
// 비밀(디바이스 토큰, ocm_ 토큰)은 이 파일에만 존재한다. 플랫폼 서버로 전송되지 않는다.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

export interface RunnerConfig {
  platformUrl: string;
  gatewayUrl: string;
  deviceToken?: string;
  agentId?: string;
  handle?: string;
  opencrab?: {
    token: string; // ocm_ token — never leaves this machine
    packId: string;
    mcpUrl?: string;
    workspaceId?: string; // persona 쿼리 스코프 — 대형 테넌트의 statement timeout 회피
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

const DEFAULTS: RunnerConfig = {
  platformUrl: "http://localhost:3000",
  gatewayUrl: "ws://localhost:8787",
  brain: { provider: "claude" },
  limits: { concurrency: 3, repliesPerHour: 30 },
};

export function loadConfig(): RunnerConfig {
  if (!existsSync(CONFIG_PATH)) return { ...DEFAULTS };
  try {
    const raw = JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
    return { ...DEFAULTS, ...raw, limits: { ...DEFAULTS.limits, ...raw.limits }, brain: { ...DEFAULTS.brain, ...raw.brain } };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveConfig(config: RunnerConfig): void {
  mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");
}

export const configPath = CONFIG_PATH;
