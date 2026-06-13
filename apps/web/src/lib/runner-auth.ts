import { createHash, randomBytes } from "crypto";
import { prisma } from "@opencanal/db";
import type { Agent, RunnerDevice } from "@opencanal/db";

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export function generateDeviceToken(): string {
  return "ocd_" + randomBytes(32).toString("base64url");
}

export function generatePairingCode(): string {
  // 8-char, unambiguous alphabet (no 0/O/1/I)
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = randomBytes(8);
  let code = "";
  for (let i = 0; i < 8; i++) code += alphabet[bytes[i] % alphabet.length];
  return code;
}

/** Authenticate a runner request by its Bearer device token. */
export async function authenticateRunner(
  req: Request
): Promise<(RunnerDevice & { agent: Agent }) | null> {
  const header = req.headers.get("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!token) return null;
  const device = await prisma.runnerDevice.findUnique({
    where: { tokenHash: hashToken(token) },
    include: { agent: true },
  });
  return device;
}
