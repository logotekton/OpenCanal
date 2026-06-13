// Web → Gateway internal notification (fire-and-forget).
// 게이트웨이가 죽어 있어도 메시지/지시는 DB에 pending으로 남고, 러너 재접속 시 inbox로 드레인된다.

const GATEWAY_HTTP_URL = process.env.GATEWAY_HTTP_URL ?? "http://localhost:8787";
const SECRET = process.env.GATEWAY_INTERNAL_SECRET ?? "dev-internal-secret";

type NotifyPayload =
  | { kind: "room.message"; targetAgentId: string; messageId: string }
  | { kind: "room.instruction"; targetAgentId: string; instructionId: string };

export async function notifyGateway(payload: NotifyPayload): Promise<void> {
  try {
    await fetch(`${GATEWAY_HTTP_URL}/internal/notify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-internal-secret": SECRET },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    // gateway down — runner will drain via inbox on reconnect
  }
}
