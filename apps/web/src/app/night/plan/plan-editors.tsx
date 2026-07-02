"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { NIGHT_POLICY_KINDS, type NightPolicyKind } from "@opencanal/shared";

interface Policy {
  id: string;
  kind: string;
  text: string;
  active: boolean;
}
interface Directive {
  id: string;
  content: string;
  active: boolean;
}
interface Task {
  id: string;
  title: string;
  brief: string;
  originNote: string | null;
  status: string;
}

const KIND_LABEL: Record<NightPolicyKind, string> = {
  decision: "판단 기준 — 무엇을 할 가치가 있는가",
  red_flag: "금지선 — 레드 플래그 (위반하느니 건너뛴다)",
  style: "나다움 — 스타일",
  playbook: "요령 — 플레이북",
};

async function send(url: string, method: string, body?: unknown): Promise<boolean> {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const d = (await r.json().catch(() => ({}))) as { error?: string };
    alert(d.error ?? "처리에 실패했습니다.");
    return false;
  }
  return true;
}

// ───────────────────────── 판단 정책 ─────────────────────────
export function PolicyEditor({ agentId, policies }: { agentId: string; policies: Policy[] }) {
  const router = useRouter();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function add(kind: NightPolicyKind) {
    const text = (drafts[kind] ?? "").trim();
    if (!text) return;
    setBusy(true);
    const ok = await send("/api/night/policies", "POST", { agentId, kind, text });
    setBusy(false);
    if (ok) {
      setDrafts((d) => ({ ...d, [kind]: "" }));
      router.refresh();
    }
  }

  async function saveEdit(id: string) {
    const text = (editing[id] ?? "").trim();
    if (!text) return;
    setBusy(true);
    const ok = await send(`/api/night/policies/${id}`, "PATCH", { text });
    setBusy(false);
    if (ok) {
      setEditing((e) => {
        const next = { ...e };
        delete next[id];
        return next;
      });
      router.refresh();
    }
  }

  async function toggle(p: Policy) {
    if (await send(`/api/night/policies/${p.id}`, "PATCH", { active: !p.active })) router.refresh();
  }
  async function remove(id: string) {
    if (await send(`/api/night/policies/${id}`, "DELETE")) router.refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      {NIGHT_POLICY_KINDS.map((kind) => {
        const items = policies.filter((p) => p.kind === kind);
        return (
          <div key={kind} className="card">
            <p className="display-sm mb-1">{KIND_LABEL[kind]}</p>
            <div className="mt-3 flex flex-col gap-2">
              {items.length === 0 && <p className="text-sm text-mute">아직 정책이 없습니다.</p>}
              {items.map((p) =>
                editing[p.id] !== undefined ? (
                  <div key={p.id} className="flex flex-col gap-2 border-b border-hairline pb-3">
                    <textarea
                      className="input"
                      rows={2}
                      value={editing[p.id]}
                      onChange={(e) => setEditing((s) => ({ ...s, [p.id]: e.target.value }))}
                    />
                    <div className="flex gap-2">
                      <button className="pill pill-sunset pill-sm" disabled={busy} onClick={() => saveEdit(p.id)}>
                        저장
                      </button>
                      <button
                        className="pill pill-sm"
                        onClick={() =>
                          setEditing((s) => {
                            const n = { ...s };
                            delete n[p.id];
                            return n;
                          })
                        }
                      >
                        취소
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    key={p.id}
                    className="flex items-start justify-between gap-3 border-b border-hairline pb-2"
                  >
                    <p className={`flex-1 text-sm ${p.active ? "text-body" : "text-mute line-through"}`}>
                      {p.text}
                    </p>
                    <div className="flex shrink-0 gap-1">
                      <button
                        className="pill pill-sm"
                        onClick={() => setEditing((s) => ({ ...s, [p.id]: p.text }))}
                      >
                        수정
                      </button>
                      <button className="pill pill-sm" onClick={() => toggle(p)}>
                        {p.active ? "비활성" : "활성"}
                      </button>
                      <button className="pill pill-sm" onClick={() => remove(p.id)}>
                        삭제
                      </button>
                    </div>
                  </div>
                )
              )}
            </div>
            <div className="mt-3 flex gap-2">
              <input
                className="input"
                placeholder="새 정책 문장"
                value={drafts[kind] ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [kind]: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && add(kind)}
              />
              <button className="pill pill-sunset pill-sm" disabled={busy} onClick={() => add(kind)}>
                추가
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ───────────────────────── 상시 지시 ─────────────────────────
export function DirectiveEditor({ agentId, directives }: { agentId: string; directives: Directive[] }) {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!draft.trim()) return;
    setBusy(true);
    const ok = await send("/api/night/directives", "POST", { agentId, content: draft.trim() });
    setBusy(false);
    if (ok) {
      setDraft("");
      router.refresh();
    }
  }
  async function toggle(d: Directive) {
    if (await send(`/api/night/directives/${d.id}`, "PATCH", { active: !d.active })) router.refresh();
  }
  async function remove(id: string) {
    if (await send(`/api/night/directives/${id}`, "DELETE")) router.refresh();
  }

  return (
    <div className="card">
      <div className="flex flex-col gap-2">
        {directives.length === 0 && <p className="text-sm text-mute">아직 상시 지시가 없습니다.</p>}
        {directives.map((d) => (
          <div key={d.id} className="flex items-start justify-between gap-3 border-b border-hairline pb-2">
            <p className={`flex-1 text-sm ${d.active ? "text-body" : "text-mute line-through"}`}>
              {d.content}
            </p>
            <div className="flex shrink-0 gap-1">
              <button className="pill pill-sm" onClick={() => toggle(d)}>
                {d.active ? "비활성" : "활성"}
              </button>
              <button className="pill pill-sm" onClick={() => remove(d.id)}>
                삭제
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          className="input"
          placeholder="새 상시 지시 (예: BIMGraph 문서화가 밀려 있으면 항상 우선)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button className="pill pill-sunset pill-sm" disabled={busy} onClick={add}>
          추가
        </button>
      </div>
    </div>
  );
}

// ───────────────────────── 작업 카드 백로그 ─────────────────────────
const TASK_STATUS_LABEL: Record<string, string> = {
  queued: "대기",
  running: "진행",
  produced: "산출",
  skipped: "건너뜀",
  failed: "실패",
};

export function TaskEditor({ agentId, tasks }: { agentId: string; tasks: Task[] }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!title.trim() || !brief.trim()) return;
    setBusy(true);
    const ok = await send("/api/night/tasks", "POST", {
      agentId,
      title: title.trim(),
      brief: brief.trim(),
      originNote: note.trim() || undefined,
    });
    setBusy(false);
    if (ok) {
      setTitle("");
      setBrief("");
      setNote("");
      router.refresh();
    }
  }
  async function remove(id: string) {
    if (await send(`/api/night/tasks/${id}`, "DELETE")) router.refresh();
  }

  const queued = tasks.filter((t) => t.status === "queued");
  const done = tasks.filter((t) => t.status !== "queued");

  return (
    <div className="card">
      <div className="flex flex-col gap-3">
        {queued.length === 0 && <p className="text-sm text-mute">백로그가 비어 있습니다.</p>}
        {queued.map((t) => (
          <div key={t.id} className="flex items-start justify-between gap-3 border-b border-hairline pb-3">
            <div className="min-w-0">
              <p className="text-sm text-body">{t.title}</p>
              <p className="mt-0.5 text-xs text-mute">{t.brief}</p>
              {t.originNote && <p className="mt-0.5 text-xs text-mute italic">근거: {t.originNote}</p>}
            </div>
            <button className="pill pill-sm shrink-0" onClick={() => remove(t.id)}>
              삭제
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-col gap-2 border-t border-hairline pt-4">
        <input
          className="input"
          placeholder="작업 제목"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="input"
          rows={2}
          placeholder="브리프 — 무엇을 만들지"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
        />
        <input
          className="input"
          placeholder="근거 (선택) — 왜 이 작업인가"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button className="pill pill-sunset pill-sm self-start" disabled={busy} onClick={add}>
          작업 추가
        </button>
      </div>

      {done.length > 0 && (
        <div className="mt-4 border-t border-hairline pt-4">
          <p className="eyebrow mb-2">집어간 작업</p>
          {done.map((t) => (
            <div key={t.id} className="flex items-center justify-between py-1 text-sm">
              <span className="text-mute">{t.title}</span>
              <span className="font-mono text-[11px] tracking-wider text-mute uppercase">
                {TASK_STATUS_LABEL[t.status] ?? t.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
