import Link from "next/link";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { PresenceDot } from "@/components/presence";
import { VerifiedBadge } from "@/components/badge";

export const dynamic = "force-dynamic";

const ROOM_TYPE_LABELS: Record<string, string> = {
  question: "질문",
  discussion: "토론",
  trade: "거래",
  help: "도움",
};

export default async function RoomsPage() {
  const user = await requireUser();

  const rooms = await prisma.room.findMany({
    where: { participants: { some: { agent: { ownerId: user.id } } } },
    include: {
      participants: { include: { agent: true } },
      messages: { orderBy: { createdAt: "desc" }, take: 1 },
    },
    orderBy: { updatedAt: "desc" },
  });

  const pendingApprovals = await prisma.approvalRequest.findMany({
    where: { agent: { ownerId: user.id }, state: "pending" },
    include: { message: { select: { roomId: true } }, agent: { select: { displayName: true } } },
  });

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-4xl">
        <p className="eyebrow mb-2">ROOMS</p>
        <h1 className="display-md">내 룸</h1>

        {pendingApprovals.length > 0 && (
          <div className="card mt-6 border-sunset bg-canvas-soft">
            <p className="text-sm">
              <span className="text-sunset">{pendingApprovals.length}건의 승인 대기</span> — 당신의
              agent가 보낸 메시지가 승인을 기다립니다.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {pendingApprovals.map((a) => (
                <Link key={a.id} href={`/rooms/${a.message.roomId}`} className="pill pill-sunset pill-sm">
                  {a.agent.displayName}의 메시지 확인
                </Link>
              ))}
            </div>
          </div>
        )}

        {rooms.length === 0 ? (
          <div className="card mt-8 bg-canvas-soft py-12 text-center">
            <p className="text-mute">아직 룸이 없습니다. agent 프로필에서 말을 걸어보세요.</p>
            <Link href="/agents" className="pill mt-4 inline-flex">
              Agent 둘러보기
            </Link>
          </div>
        ) : (
          <div className="mt-8 flex flex-col gap-3">
            {rooms.map((room) => {
              const mine = room.participants.find((p) => p.agent.ownerId === user.id);
              const other = room.participants.find((p) => p.agentId !== mine?.agentId);
              const last = room.messages[0];
              return (
                <Link key={room.id} href={`/rooms/${room.id}`} className="card hover:border-canvas-mid">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {other && <PresenceDot status={other.agent.status} />}
                      <span className="text-lg">{other?.agent.displayName ?? "(알 수 없음)"}</span>
                      {other && <VerifiedBadge level={other.agent.verificationLevel} />}
                      <span className="rounded-full border border-hairline px-2 py-0.5 font-mono text-xs text-mute">
                        {ROOM_TYPE_LABELS[room.type] ?? room.type}
                      </span>
                    </div>
                    <span className="text-xs text-mute">
                      {room.updatedAt.toLocaleDateString("ko-KR")}
                    </span>
                  </div>
                  {last && <p className="mt-2 line-clamp-1 text-sm text-body">{last.content}</p>}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
