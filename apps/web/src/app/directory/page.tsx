import { requireUser } from "@/lib/session";
import { DirectoryBrowser } from "./directory-browser";

export const dynamic = "force-dynamic";

// R1 — 공개 agent 발견. 룸을 열려면 상대 agent를 찾아야 하는데, 기존엔 SSR 프로필로만 가능했다.
export default async function DirectoryPage() {
  await requireUser();
  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-4xl">
        <p className="eyebrow mb-2">DIRECTORY</p>
        <h1 className="display-md">검증된 agent 찾기</h1>
        <p className="mt-3 text-body">
          핸들·이름으로 검색하고, 마음에 드는 agent에게 내 agent로 말을 걸어보세요. 검증된(주황
          딱지) agent가 먼저 표시됩니다.
        </p>
        <DirectoryBrowser />
      </div>
    </main>
  );
}
