// OpenCanal Gateway — the realtime spine.
// Runner WS connections (device-token auth), heartbeat → presence, message fanout.

import Fastify from "fastify";
import { WebSocketServer, WebSocket } from "ws";
import { createHash, timingSafeEqual } from "crypto";
import { existsSync } from "fs";
import { join } from "path";

// Load root .env when run from the monorepo (dev). Production sets real env vars.
if (!process.env.DATABASE_URL) {
  const rootEnv = join(import.meta.dirname, "..", "..", "..", ".env");
  if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);
}

const { prisma } = await import("@opencanal/db");
import type { ServerEvent, RunnerEvent } from "@opencanal/shared";

const PORT = Number(process.env.GATEWAY_PORT ?? 8787);
const DEFAULT_SECRET = "dev-internal-secret";
const INTERNAL_SECRET = process.env.GATEWAY_INTERNAL_SECRET ?? DEFAULT_SECRET;

// H4: 프로덕션에서 기본 시크릿으로 기동 거부 — /internal/notify는 메시지 위조 경로다
if (process.env.NODE_ENV === "production" && INTERNAL_SECRET === DEFAULT_SECRET) {
  throw new Error("GATEWAY_INTERNAL_SECRET must be set to a strong value in production");
}

const SECRET_BUF = Buffer.from(INTERNAL_SECRET);

// 상수 시간 비교 — 타이밍 공격 방지
function secretMatches(provided: unknown): boolean {
  if (typeof provided !== "string") return false;
  const buf = Buffer.from(provided);
  if (buf.length !== SECRET_BUF.length) return false;
  return timingSafeEqual(buf, SECRET_BUF);
}

// agentId → live runner socket
const runners = new Map<string, WebSocket>();
// agentId → last heartbeat epoch ms
const lastBeat = new Map<string, number>();

function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

async function setStatus(agentId: string, status: "online" | "away" | "offline") {
  try {
    await prisma.agent.update({
      where: { id: agentId },
      data: { status, lastHeartbeatAt: status === "offline" ? undefined : new Date() },
    });
  } catch (err) {
    console.error(`[presence] failed to set ${agentId} → ${status}`, err);
  }
}

function send(ws: WebSocket, event: ServerEvent) {
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(event));
}

// ── HTTP app (internal notify + health) ──

const app = Fastify({ logger: false });

app.get("/health", async () => ({
  ok: true,
  connectedRunners: runners.size,
}));

// Web → gateway: a new message or owner instruction needs to reach an agent's runner
app.post("/internal/notify", async (req, reply) => {
  if (!secretMatches(req.headers["x-internal-secret"])) {
    return reply.status(401).send({ error: "unauthorized" });
  }
  const body = req.body as {
    kind: string;
    targetAgentId: string;
    messageId?: string;
    instructionId?: string;
  };

  const ws = runners.get(body.targetAgentId);
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return reply.send({ delivered: false, reason: "runner offline — queued in DB" });
  }

  if (body.kind === "room.message" && body.messageId) {
    const message = await prisma.message.findUnique({
      where: { id: body.messageId },
      include: {
        room: { select: { type: true } },
        sender: { select: { id: true, handle: true, type: true, verificationLevel: true } },
      },
    });
    if (!message) return reply.status(404).send({ error: "message not found" });

    send(ws, {
      type: "room.message",
      roomId: message.roomId,
      roomType: message.room.type,
      messageId: message.id,
      senderAgentId: message.sender.id,
      senderHandle: message.sender.handle,
      senderAgentType: message.sender.type,
      senderVerificationLevel: message.sender.verificationLevel,
      content: message.content,
      createdAt: message.createdAt.toISOString(),
    });
    return reply.send({ delivered: true });
  }

  if (body.kind === "room.instruction" && body.instructionId) {
    const instruction = await prisma.instruction.findUnique({
      where: { id: body.instructionId },
      include: {
        room: {
          select: {
            type: true,
            participants: {
              where: { agentId: { not: body.targetAgentId } },
              select: {
                agent: { select: { id: true, handle: true, type: true, verificationLevel: true } },
              },
            },
          },
        },
      },
    });
    if (!instruction) return reply.status(404).send({ error: "instruction not found" });

    const counterpart = instruction.room.participants[0]?.agent ?? null;
    send(ws, {
      type: "room.instruction",
      roomId: instruction.roomId,
      roomType: instruction.room.type,
      instructionId: instruction.id,
      content: instruction.content,
      counterpart: counterpart
        ? {
            agentId: counterpart.id,
            handle: counterpart.handle,
            agentType: counterpart.type,
            verificationLevel: counterpart.verificationLevel,
          }
        : null,
      createdAt: instruction.createdAt.toISOString(),
    });
    return reply.send({ delivered: true });
  }

  return reply.status(400).send({ error: "unknown kind" });
});

// ── WS server (runners) ──

await app.listen({ port: PORT, host: "0.0.0.0" });
console.log(`[gateway] listening on :${PORT}`);

const wss = new WebSocketServer({ server: app.server, path: "/runner" });

wss.on("connection", async (ws, req) => {
  const auth = req.headers.authorization ?? "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : null;
  if (!token) {
    ws.close(4001, "missing token");
    return;
  }

  const device = await prisma.runnerDevice.findUnique({
    where: { tokenHash: hashToken(token) },
    include: { agent: { select: { id: true, handle: true } } },
  });
  if (!device) {
    ws.close(4003, "invalid token");
    return;
  }

  const agentId = device.agent.id;

  // Replace any previous connection for this agent
  runners.get(agentId)?.close(4000, "replaced by new connection");
  runners.set(agentId, ws);
  lastBeat.set(agentId, Date.now());

  await Promise.all([
    setStatus(agentId, "online"),
    prisma.runnerDevice.update({ where: { id: device.id }, data: { lastSeenAt: new Date() } }),
  ]);

  const pendingCount = await prisma.message.count({
    where: {
      room: { participants: { some: { agentId } } },
      senderAgentId: { not: agentId },
      status: "pending",
    },
  });

  send(ws, { type: "hello", agentId, handle: device.agent.handle, pendingCount });
  console.log(`[gateway] runner connected: @${device.agent.handle} (pending: ${pendingCount})`);

  ws.on("message", async (raw) => {
    let event: RunnerEvent;
    try {
      event = JSON.parse(raw.toString());
    } catch {
      return;
    }
    if (event.type === "heartbeat") {
      lastBeat.set(agentId, Date.now());
      const desired = event.busy ? "away" : "online";
      await setStatus(agentId, desired);
    }
  });

  ws.on("close", async () => {
    if (runners.get(agentId) === ws) {
      runners.delete(agentId);
      lastBeat.delete(agentId);
      await setStatus(agentId, "offline");
      console.log(`[gateway] runner disconnected: @${device.agent.handle}`);
    }
  });
});

// Sweep: stale heartbeats → offline (60s threshold)
setInterval(async () => {
  const now = Date.now();
  for (const [agentId, beat] of lastBeat) {
    if (now - beat > 60_000) {
      const ws = runners.get(agentId);
      ws?.terminate();
      runners.delete(agentId);
      lastBeat.delete(agentId);
      await setStatus(agentId, "offline");
    }
  }
}, 30_000);
