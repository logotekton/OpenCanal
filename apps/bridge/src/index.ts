// OpenCanal Telegram bridge (R1) — owners instruct/approve/get-notified from chat.
// 룸 구조는 그대로. 텔레그램은 "소유자 ↔ 자기 agent" 채널일 뿐 — 상대 agent와 직접 대화하지 않는다.
// 플랫폼과는 내부 시크릿(x-bridge-secret)으로 /api/bridge/* 를 통해 대화한다.
// TELEGRAM_BOT_TOKEN이 없으면 idle(no-op)로 종료한다.

import { existsSync } from "fs";
import { join } from "path";

// 모노레포 dev에서 루트 .env 로드 (프로덕션은 실제 env 사용)
if (!process.env.TELEGRAM_BOT_TOKEN || !process.env.BRIDGE_INTERNAL_SECRET) {
  const rootEnv = join(import.meta.dirname, "..", "..", "..", ".env");
  if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);
}

const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const PLATFORM = process.env.PLATFORM_URL ?? "http://localhost:3000";
const SECRET = process.env.BRIDGE_INTERNAL_SECRET ?? "dev-internal-secret";
const TG = `https://api.telegram.org/bot${TOKEN}`;

if (!TOKEN) {
  console.log("[bridge] TELEGRAM_BOT_TOKEN 미설정 — 브리지는 idle 상태로 종료합니다.");
  console.log("[bridge] 봇 토큰을 설정하면 /pair · 승인 버튼 · 알림 푸시가 가동됩니다.");
  process.exit(0);
}

// ── Platform internal calls ──
async function platform(method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(`${PLATFORM}${path}`, {
    method,
    headers: { "Content-Type": "application/json", "x-bridge-secret": SECRET },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15_000),
  });
}

// ── Telegram API ──
interface InlineButton {
  text: string;
  callback_data: string;
}
async function tg(method: string, payload: Record<string, unknown>): Promise<unknown> {
  const res = await fetch(`${TG}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(40_000),
  });
  return res.json().catch(() => ({}));
}
function sendMessage(chatId: string | number, text: string, buttons?: InlineButton[][]) {
  return tg("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
    ...(buttons ? { reply_markup: { inline_keyboard: buttons } } : {}),
  });
}

const HELP =
  "OpenCanal 브리지에 오신 것을 환영합니다.\n" +
  "웹에서 발급한 코드로 연결하세요: <code>/pair &lt;코드&gt;</code>\n" +
  "연결되면 승인 요청·거래 알림을 여기서 받고, 버튼으로 승인/반려할 수 있습니다.";

// ── Update handling ──
async function handleMessage(msg: { chat: { id: number }; text?: string }): Promise<void> {
  const chatId = msg.chat.id;
  const text = (msg.text ?? "").trim();

  if (text === "/start" || text === "/help") {
    await sendMessage(chatId, HELP);
    return;
  }
  if (text.toLowerCase().startsWith("/pair")) {
    const code = text.split(/\s+/)[1];
    if (!code) {
      await sendMessage(chatId, "코드를 함께 보내세요: <code>/pair ABCD1234</code>");
      return;
    }
    const res = await platform("POST", "/api/bridge/pair", { code, chatId });
    if (res.ok) await sendMessage(chatId, "✅ 연결되었습니다. 이제 알림을 여기서 받습니다.");
    else {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      await sendMessage(chatId, `연결 실패: ${data.error ?? res.status}`);
    }
    return;
  }
  await sendMessage(chatId, HELP);
}

async function handleCallback(cb: {
  id: string;
  data?: string;
  message?: { chat: { id: number }; message_id: number };
}): Promise<void> {
  const chatId = cb.message?.chat.id;
  const [action, approvalId] = (cb.data ?? "").split(":");
  if (!chatId || (action !== "approve" && action !== "reject") || !approvalId) {
    await tg("answerCallbackQuery", { callback_query_id: cb.id });
    return;
  }
  const decision = action === "approve" ? "approved" : "rejected";
  const res = await platform("POST", "/api/bridge/approve", { chatId, approvalId, decision });
  const label = res.ok ? (decision === "approved" ? "승인됨 ✅" : "반려됨") : "처리 실패";
  await tg("answerCallbackQuery", { callback_query_id: cb.id, text: label });
  if (cb.message) {
    await tg("editMessageReplyMarkup", {
      chat_id: chatId,
      message_id: cb.message.message_id,
      reply_markup: { inline_keyboard: [[{ text: label, callback_data: "noop" }]] },
    });
  }
}

// ── getUpdates long-poll loop ──
async function pollUpdates(): Promise<void> {
  let offset = 0;
  for (;;) {
    try {
      const r = (await tg("getUpdates", { offset, timeout: 30 })) as {
        ok?: boolean;
        result?: {
          update_id: number;
          message?: { chat: { id: number }; text?: string };
          callback_query?: { id: string; data?: string; message?: { chat: { id: number }; message_id: number } };
        }[];
      };
      for (const u of r.result ?? []) {
        offset = u.update_id + 1;
        if (u.message) await handleMessage(u.message).catch((e) => console.error("[bridge] msg:", e));
        if (u.callback_query)
          await handleCallback(u.callback_query).catch((e) => console.error("[bridge] cb:", e));
      }
    } catch (e) {
      console.error("[bridge] getUpdates:", e instanceof Error ? e.message : e);
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

// ── Outbox push loop (notifications → telegram) ──
const KIND_LABEL: Record<string, string> = {
  approval_required: "승인 필요",
  receipt_created: "거래 확정",
  receipt_fulfilled: "이행 완료",
  receipt_disputed: "분쟁",
  instruction_failed: "지시 실패",
  verification_reviewed: "검증 결과",
};

async function pushOutbox(): Promise<void> {
  let since = new Date().toISOString(); // 기동 이후 알림만
  for (;;) {
    await new Promise((r) => setTimeout(r, 5000));
    try {
      const res = await platform("GET", `/api/bridge/outbox?since=${encodeURIComponent(since)}`);
      if (!res.ok) continue;
      const { notifications } = (await res.json()) as {
        notifications: {
          chatId: string;
          kind: string;
          title: string;
          body: string | null;
          href: string | null;
          approvalId: string | null;
          createdAt: string;
        }[];
      };
      for (const n of notifications) {
        const tag = KIND_LABEL[n.kind] ?? n.kind;
        const link = n.href ? `\n${PLATFORM}${n.href}` : "";
        const text = `<b>[${tag}]</b> ${n.title}${n.body ? `\n${n.body}` : ""}${link}`;
        const buttons =
          n.kind === "approval_required" && n.approvalId
            ? [
                [
                  { text: "승인", callback_data: `approve:${n.approvalId}` },
                  { text: "반려", callback_data: `reject:${n.approvalId}` },
                ],
              ]
            : undefined;
        await sendMessage(n.chatId, text, buttons).catch((e) => console.error("[bridge] push:", e));
        if (n.createdAt > since) since = n.createdAt;
      }
    } catch (e) {
      console.error("[bridge] outbox:", e instanceof Error ? e.message : e);
    }
  }
}

console.log(`[bridge] started — platform ${PLATFORM}`);
void pollUpdates();
void pushOutbox();
