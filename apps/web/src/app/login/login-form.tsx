"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function LoginForm({
  devLoginEnabled,
  googleEnabled,
}: {
  devLoginEnabled: boolean;
  googleEnabled: boolean;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleDevLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const res = await signIn("dev-email", { email, name, redirect: false });
    setLoading(false);
    if (res?.error) {
      setError("로그인에 실패했습니다. 이메일을 확인해주세요.");
    } else {
      router.push("/agents");
      router.refresh();
    }
  }

  return (
    <div className="mt-6 flex flex-col gap-4">
      {googleEnabled && (
        <button
          className="pill justify-center"
          onClick={() => signIn("google", { callbackUrl: "/agents" })}
        >
          Google로 계속하기
        </button>
      )}

      {googleEnabled && devLoginEnabled && (
        <div className="flex items-center gap-3 text-xs text-mute">
          <div className="h-px flex-1 bg-hairline" />
          또는
          <div className="h-px flex-1 bg-hairline" />
        </div>
      )}

      {devLoginEnabled && (
        <form onSubmit={handleDevLogin} className="flex flex-col gap-4">
          <p className="text-sm text-mute">
            개발용 로그인 — 이메일만으로 입장합니다. 신원 검증은 agent 딱지 레이어에서 별도로
            이루어집니다.
          </p>
          <input
            type="email"
            required
            placeholder="you@example.com"
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            type="text"
            placeholder="이름 (선택)"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          {error && <p className="text-sm text-sunset">{error}</p>}
          <button type="submit" disabled={loading} className="pill pill-primary justify-center">
            {loading ? "..." : "로그인"}
          </button>
        </form>
      )}

      {!googleEnabled && !devLoginEnabled && (
        <p className="text-sm text-sunset">
          로그인 방법이 설정되지 않았습니다. 관리자에게 문의하세요 (AUTH_GOOGLE_* 또는
          ALLOW_DEV_LOGIN 설정 필요).
        </p>
      )}
    </div>
  );
}
