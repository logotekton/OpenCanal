// Outbound-only WebSocket to the gateway. No inbound ports, no firewall config.

import WebSocket from "ws";
import type { ServerEvent } from "@opencanal/shared";
import type { RunnerConfig } from "./config";
import type { AgentLoop } from "./agent-loop";

export function startWsClient(config: RunnerConfig, loop: AgentLoop): void {
  let attempt = 0;

  function connect(): void {
    const ws = new WebSocket(`${config.gatewayUrl}/runner`, {
      headers: { Authorization: `Bearer ${config.deviceToken}` },
    });

    let heartbeat: ReturnType<typeof setInterval> | null = null;

    ws.on("open", () => {
      attempt = 0;
      console.log(`[ws] connected to gateway (${config.gatewayUrl})`);
      heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "heartbeat", busy: loop.queue.busy }));
        }
      }, 20_000);
      // Drain anything that piled up while offline
      loop
        .drainInbox()
        .then((n) => n > 0 && console.log(`[ws] drained ${n} pending message(s)`))
        .catch((err) => console.error("[ws] inbox drain failed:", err.message));
      // 거래 이력을 OpenCrab 학습 메모리에 ingest (ocm_ 없으면 no-op)
      loop
        .ingestReceipts()
        .catch((err) => console.error("[ws] receipt ingest failed:", err.message));
    });

    ws.on("message", (raw) => {
      let event: ServerEvent;
      try {
        event = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (event.type === "hello") {
        console.log(`[ws] hello @${event.handle} — pending: ${event.pendingCount}`);
      } else if (event.type === "room.message") {
        loop.handleMessage(event);
      } else if (event.type === "room.instruction") {
        loop.handleInstruction(event);
      }
    });

    ws.on("close", (code, reason) => {
      if (heartbeat) clearInterval(heartbeat);
      if (code === 4003) {
        console.error("[ws] device token rejected — run `opencanal-runner login` again");
        process.exit(1);
      }
      const delay = Math.min(30_000, 1000 * 2 ** attempt++);
      console.log(`[ws] disconnected (${code} ${reason}) — reconnecting in ${delay / 1000}s`);
      setTimeout(connect, delay);
    });

    ws.on("error", (err) => {
      console.error(`[ws] error: ${err.message}`);
      ws.close();
    });
  }

  connect();
}
