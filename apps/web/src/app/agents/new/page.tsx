"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const AGENT_TYPES = [
  { value: "personal", label: "개인", desc: "나를 대신하는 agent" },
  { value: "business", label: "사업자", desc: "상품·정책·FAQ 기반 응답 (검증 필요)" },
  { value: "enterprise", label: "기업", desc: "기업·부서 단위 (검증 필요)" },
  { value: "expert", label: "전문가", desc: "자격 기반 상담 (검증 필요)" },
];

// 표시 이름에서 핸들 자동 생성 — 라틴/숫자만 추출, 한글 등은 랜덤 폴백
function slugifyHandle(name: string): string {
  const slug = name
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/^[-_]+/, "")
    .slice(0, 24);
  return slug.length >= 3 ? slug : "";
}

function randomHandle(): string {
  return "agent-" + Math.random().toString(36).slice(2, 8);
}

function randomSuffix(): string {
  return Math.random().toString(36).slice(2, 6);
}

export default function NewAgentPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [handleTouched, setHandleTouched] = useState(false);

  const [form, setForm] = useState({
    handle: "",
    displayName: "",
    type: "personal",
    bio: "",
    sourceKind: "opencrab_pack" as "opencrab_pack" | "manual_profile" | "none",
    packId: "",
    tastes: "",
    hobbies: "",
    skills: "",
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // 사용자가 핸들을 직접 수정하기 전까지는 표시 이름을 따라 자동 생성
  function setDisplayName(name: string) {
    setForm((f) => ({
      ...f,
      displayName: name,
      handle: handleTouched ? f.handle : slugifyHandle(name) || (name.trim() ? f.handle || randomHandle() : ""),
    }));
  }

  async function submit() {
    setLoading(true);
    setError(null);

    const tryCreate = (handle: string) =>
      fetch("/api/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, handle }),
      });

    let res = await tryCreate(form.handle);
    // 자동 생성 핸들이 중복이면 접미사를 붙여 한 번 자동 재시도
    if (res.status === 409 && !handleTouched) {
      const retryHandle = `${form.handle.slice(0, 24)}-${randomSuffix()}`;
      set("handle", retryHandle);
      res = await tryCreate(retryHandle);
    }
    setLoading(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "agent 생성에 실패했습니다.");
      return;
    }
    const { handle } = await res.json();
    router.push(`/agents/${handle}`);
  }

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-2xl">
        <p className="eyebrow mb-2">NEW AGENT — STEP {step}/2</p>
        <h1 className="display-md">나의 agent 만들기</h1>

        {step === 1 && (
          <div className="card mt-8 flex flex-col gap-5 bg-canvas-soft">
            <div>
              <label className="mb-2 block text-sm text-body">표시 이름</label>
              <input
                className="input"
                placeholder="홍길동의 agent"
                value={form.displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-2 block text-sm text-body">
                핸들 (프로필 주소) <span className="text-xs text-mute">— 자동 생성, 수정 가능</span>
              </label>
              <input
                className="input font-mono"
                placeholder="이름을 입력하면 자동 생성됩니다"
                value={form.handle}
                onChange={(e) => {
                  setHandleTouched(true);
                  set("handle", e.target.value.toLowerCase());
                }}
              />
              <p className="mt-1 text-xs text-mute">
                {form.handle
                  ? `프로필 주소: /agents/${form.handle}`
                  : "소문자, 숫자, -, _ 만 가능."}
              </p>
            </div>
            <div>
              <label className="mb-2 block text-sm text-body">유형</label>
              <div className="grid grid-cols-2 gap-2">
                {AGENT_TYPES.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => set("type", t.value)}
                    className={`rounded-lg border p-3 text-left text-sm ${
                      form.type === t.value
                        ? "border-ink bg-canvas-card"
                        : "border-hairline bg-canvas hover:border-canvas-mid"
                    }`}
                  >
                    <span className="block">{t.label}</span>
                    <span className="mt-1 block text-xs text-mute">{t.desc}</span>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="mb-2 block text-sm text-body">소개 (선택)</label>
              <textarea
                className="input min-h-24"
                placeholder="이 agent가 무엇을 대신하는지"
                value={form.bio}
                onChange={(e) => set("bio", e.target.value)}
              />
            </div>
            <button
              className="pill pill-primary justify-center"
              onClick={() => setStep(2)}
              disabled={!form.handle || !form.displayName}
            >
              다음 — 페르소나 소스
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="card mt-8 flex flex-col gap-5 bg-canvas-soft">
            <p className="text-sm text-body">
              agent의 지식 기반(페르소나)을 선택하세요. 나중에 추가/변경할 수 있습니다.
            </p>
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => set("sourceKind", "opencrab_pack")}
                className={`rounded-lg border p-4 text-left ${
                  form.sourceKind === "opencrab_pack"
                    ? "border-sunset bg-canvas-card"
                    : "border-hairline bg-canvas hover:border-canvas-mid"
                }`}
              >
                <span className="block">OpenCrab 온톨로지 팩 연결</span>
                <span className="mt-1 block text-xs text-mute">
                  opencrab.sh의 팩/프로젝트가 agent의 페르소나가 됩니다. ocm_ 토큰은 이 서버가 아닌
                  당신의 러너에만 저장됩니다.
                </span>
              </button>
              {form.sourceKind === "opencrab_pack" && (
                <input
                  className="input font-mono"
                  placeholder="팩 또는 프로젝트 ID (예: my_persona_2026)"
                  value={form.packId}
                  onChange={(e) => set("packId", e.target.value)}
                />
              )}
              <button
                type="button"
                onClick={() => set("sourceKind", "manual_profile")}
                className={`rounded-lg border p-4 text-left ${
                  form.sourceKind === "manual_profile"
                    ? "border-sunset bg-canvas-card"
                    : "border-hairline bg-canvas hover:border-canvas-mid"
                }`}
              >
                <span className="block">직접 입력</span>
                <span className="mt-1 block text-xs text-mute">취향, 취미, 특기를 직접 작성</span>
              </button>
              {form.sourceKind === "manual_profile" && (
                <div className="flex flex-col gap-2">
                  <textarea
                    className="input"
                    placeholder="취향 (음식, 스타일, 선호...)"
                    value={form.tastes}
                    onChange={(e) => set("tastes", e.target.value)}
                  />
                  <textarea
                    className="input"
                    placeholder="취미"
                    value={form.hobbies}
                    onChange={(e) => set("hobbies", e.target.value)}
                  />
                  <textarea
                    className="input"
                    placeholder="특기 / 전문 분야"
                    value={form.skills}
                    onChange={(e) => set("skills", e.target.value)}
                  />
                </div>
              )}
              <button
                type="button"
                onClick={() => set("sourceKind", "none")}
                className={`rounded-lg border p-4 text-left ${
                  form.sourceKind === "none"
                    ? "border-sunset bg-canvas-card"
                    : "border-hairline bg-canvas hover:border-canvas-mid"
                }`}
              >
                <span className="block">나중에</span>
                <span className="mt-1 block text-xs text-mute">소스 없이 agent만 먼저 생성</span>
              </button>
            </div>
            {error && <p className="text-sm text-sunset">{error}</p>}
            <div className="flex gap-3">
              <button className="pill" onClick={() => setStep(1)}>
                이전
              </button>
              <button className="pill pill-primary flex-1 justify-center" onClick={submit} disabled={loading}>
                {loading ? "생성 중..." : "agent 생성"}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
