// R0 라이브 증명 — 실제 Claude 두뇌로 두 agent가 룸에서 대화한다.
// 러너의 실제 ClaudeAdapter + buildConstitution + 플랫폼 룸 루프를 그대로 사용.
// 실행: pnpm --filter opencanal-runner exec tsx scripts/live-proof.ts
import { buildConstitution } from "@opencanal/shared";
import { ClaudeAdapter } from "../src/brain/claude";
import { parseBrainOutput } from "../src/brain/adapter";

const BASE = "http://localhost:3000";
const brain = new ClaudeAdapter();

class Session {
  cookies = new Map<string, string>();
  cookieHeader() {
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
  }
  absorb(res: Response) {
    for (const c of (res.headers as any).getSetCookie?.() ?? []) {
      const [pair] = c.split(";");
      const i = pair.indexOf("=");
      this.cookies.set(pair.slice(0, i).trim(), pair.slice(i + 1).trim());
    }
  }
  async fetch(path: string, options: any = {}) {
    const res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: { ...(options.headers ?? {}), cookie: this.cookieHeader() },
      redirect: "manual",
    });
    this.absorb(res);
    return res;
  }
  async login(email: string, name: string) {
    const { csrfToken } = await (await this.fetch("/api/auth/csrf")).json();
    await this.fetch("/api/auth/callback/dev-email", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ csrfToken, email, name }),
    });
    const s = await (await this.fetch("/api/auth/session")).json();
    if (!s?.user?.email) throw new Error("login failed");
    return s.user;
  }
  async json(path: string, options?: any) {
    const res = await this.fetch(path, options);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(`${path} → ${res.status}: ${JSON.stringify(body)}`);
    return body;
  }
}
const post = (b: any) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

interface Persona {
  handle: string;
  displayName: string;
  block: string;
}

// 러너 한 명을 흉내내는 드라이버 — 실제 두뇌로 inbox를 처리한다
class RunnerDriver {
  constructor(
    private deviceToken: string,
    private persona: Persona
  ) {}
  private h() {
    return { Authorization: `Bearer ${this.deviceToken}`, "Content-Type": "application/json" };
  }
  async inbox() {
    return (await fetch(`${BASE}/api/runner/inbox`, { headers: this.h() })).json();
  }
  async history(roomId: string) {
    const r = await fetch(`${BASE}/api/runner/rooms/${roomId}/history`, { headers: this.h() });
    return r.ok ? r.json() : { messages: [] };
  }
  private async compose(roomId: string, roomType: string, counterpart: any, tail: string) {
    const hist = await this.history(roomId);
    const sys = buildConstitution({
      agentHandle: this.persona.handle,
      agentDisplayName: this.persona.displayName,
      roomType: roomType as any,
      counterpart,
      personaBlock: this.persona.block,
    });
    const transcript = hist.messages.map((m: any) => `@${m.senderHandle}: ${m.content}`).join("\n");
    const userPrompt = [transcript && `# Conversation so far\n${transcript}`, tail].filter(Boolean).join("\n\n");
    const raw = await brain.complete(sys, userPrompt);
    return parseBrainOutput(raw);
  }
  // 한 사이클: 지시 1건 또는 상대 메시지 1건을 처리
  async tick(): Promise<string | null> {
    const inbox = await this.inbox();
    if (inbox.instructions?.length) {
      const ins = inbox.instructions[0];
      const cp = ins.counterpart
        ? { handle: ins.counterpart.handle, type: ins.counterpart.agentType, verificationLevel: ins.counterpart.verificationLevel }
        : { handle: "unknown", type: "personal", verificationLevel: "L0" };
      const out = await this.compose(
        ins.roomId, ins.roomType, cp,
        `# Instruction from your OWNER (not visible to counterpart)\n${ins.content}\n\nCompose the message YOU send to @${cp.handle}. Speak in your own voice as the owner's delegate. Output format exactly.`
      );
      const r = await fetch(`${BASE}/api/runner/messages`, {
        headers: this.h(),
        method: "POST",
        body: JSON.stringify({ roomId: ins.roomId, instructionId: ins.instructionId, content: out.content, claims: out.claims, needsApproval: out.needs_approval }),
      });
      if (!r.ok) throw new Error(`reply(instruction) ${r.status}: ${await r.text()}`);
      return `[@${this.persona.handle} ←지시]\n${out.content}`;
    }
    if (inbox.messages?.length) {
      const msg = inbox.messages[0];
      const cp = { handle: msg.senderHandle, type: msg.senderAgentType, verificationLevel: msg.senderVerificationLevel };
      const out = await this.compose(
        msg.roomId, msg.roomType, cp,
        `# New message from @${msg.senderHandle}\n${msg.content}\n\nReply now as @${this.persona.handle}, following the output format exactly.`
      );
      const r = await fetch(`${BASE}/api/runner/messages`, {
        headers: this.h(),
        method: "POST",
        body: JSON.stringify({ roomId: msg.roomId, inReplyToId: msg.messageId, content: out.content, claims: out.claims, needsApproval: out.needs_approval }),
      });
      if (!r.ok) throw new Error(`reply(message) ${r.status}: ${await r.text()}`);
      return `[@${this.persona.handle} →응답]\n${out.content}`;
    }
    return null;
  }
}

async function pair(owner: Session, agentId: string) {
  const p = await owner.json(`/api/agents/${agentId}/pairing`, { method: "POST" });
  const paired = await (await fetch(`${BASE}/api/runner/pair`, post({ code: p.code, deviceName: "live-proof" }))).json();
  return paired.deviceToken as string;
}

async function main() {
  const sfx = Date.now().toString(36);
  console.log("=== R0 라이브 증명: 실제 Claude 두뇌 agent 대화 ===\n");

  const aliceP: Persona = {
    handle: `live-alice-${sfx}`, displayName: "민지의 agent",
    block: "## Owner profile\n이름은 민지(공개 가능). 주말엔 북한산 등산을 즐기고 매운 음식을 좋아함. 사진(필름카메라) 취미. 성격은 적극적이고 계획적. 새로운 사람과 함께 야외활동 하는 걸 선호.",
  };
  const bobP: Persona = {
    handle: `live-bob-${sfx}`, displayName: "준호의 agent",
    block: "## Owner profile\n이름은 준호(공개 가능). 클라이밍과 백패킹을 좋아하고, 요리(특히 매운 한식)에 관심 많음. 내향적이지만 취미가 맞으면 잘 어울림. 주말 오전을 선호.",
  };

  const alice = new Session(); await alice.login(`${aliceP.handle}@test.com`, "민지");
  const bob = new Session(); await bob.login(`${bobP.handle}@test.com`, "준호");

  const aliceAgent = await alice.json("/api/agents", post({ handle: aliceP.handle, displayName: aliceP.displayName, type: "personal", sourceKind: "manual_profile", tastes: "매운 음식", hobbies: "북한산 등산, 필름사진", skills: "" }));
  const bobAgent = await bob.json("/api/agents", post({ handle: bobP.handle, displayName: bobP.displayName, type: "personal", sourceKind: "manual_profile", tastes: "매운 한식", hobbies: "클라이밍, 백패킹", skills: "요리" }));
  console.log(`agents: @${aliceP.handle}, @${bobP.handle}`);

  const aliceTok = await pair(alice, aliceAgent.id);
  const bobTok = await pair(bob, bobAgent.id);
  const aliceRunner = new RunnerDriver(aliceTok, aliceP);
  const bobRunner = new RunnerDriver(bobTok, bobP);

  const room = await alice.json("/api/rooms", post({ targetAgentId: bobAgent.id, initiatorAgentId: aliceAgent.id, type: "question" }));
  console.log(`room: ${room.roomId} (question)\n`);

  // 민지가 자기 agent에게 지시 — 이후 두 agent는 자동으로 핑퐁
  await alice.json(`/api/rooms/${room.roomId}/instructions`, post({ content: "상대 agent에게 인사하고, 내 주말 취미를 자연스럽게 소개하면서 같이 할만한 야외활동을 제안해봐. 너무 길지 않게." }));
  console.log("[지시] 민지 → 자기 agent: 인사+취미 소개+야외활동 제안\n");

  const turns: string[] = [];
  const order = [aliceRunner, bobRunner, aliceRunner, bobRunner, aliceRunner, bobRunner];
  for (let i = 0; i < order.length; i++) {
    const out = await order[i].tick();
    if (out) { turns.push(out); console.log(out + "\n"); }
    else console.log(`(turn ${i + 1}: 처리할 항목 없음)\n`);
  }

  // 최종 스레드 (민지 시점)
  const thread = await alice.json(`/api/rooms/${room.roomId}/messages`);
  console.log("=== 최종 룸 스레드 ===");
  for (const m of thread.messages) console.log(`@${m.sender.handle}: ${m.content}`);

  return { roomId: room.roomId, turns, thread: thread.messages };
}

main().then((r) => {
  console.log(`\n✅ R0 라이브 증명 완료 — ${r.turns.length} 턴, 실제 Claude 두뇌로 대화`);
}).catch((e) => {
  console.error("R0 실패:", e);
  process.exit(1);
});
