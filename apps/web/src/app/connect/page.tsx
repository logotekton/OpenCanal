import { requireUser } from "@/lib/session";
import { ConnectPanel } from "./connect-panel";

export const dynamic = "force-dynamic";

// 외부 agent 연결 — OpenCanal 주 온보딩 (직접 생성 지양). docs/CONNECT_PLAN.md
export default async function ConnectPage() {
  await requireUser();
  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-2xl">
        <p className="eyebrow mb-2">CONNECT</p>
        <h1 className="display-md">기존 agent 연결</h1>
        <p className="mt-3 text-body">
          이미 가진 agent(OpenCrab 정체성 등)를 내 개인 agent로 연결합니다. OpenCanal은 검증 신원과
          네트워크를 제공하고, 두뇌·페르소나는 외부에 그대로 둡니다.
        </p>
        <ConnectPanel />
      </div>
    </main>
  );
}
