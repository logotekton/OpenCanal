import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";

// Session 리소스 (ROOM_REDESIGN Bend 4): "Intent를 받아 Receipt를 내는 거버넌스 세션"의 1급 뷰.
// Room 테이블이 곧 Session(개명은 churn이라 보류) — 이 엔드포인트가 intent+참여자(role)+
// 타입드 interaction+result를 한 리소스로 합성해 노출한다. 룸 채팅 UI는 이 세션의 한 렌더일 뿐.
export async function GET(_req: Request, { params }: { params: Promise<{ sessionId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { sessionId } = await params;
  const room = await prisma.room.findUnique({
    where: { id: sessionId },
    include: {
      intent: { select: { id: true, kind: true, spec: true, status: true } },
      participants: { include: { agent: { select: { id: true, handle: true, displayName: true, ownerId: true } } } },
      messages: {
        where: { OR: [{ approval: { in: ["none", "approved"] } }, { sender: { ownerId: user.id } }] },
        orderBy: { createdAt: "asc" },
        take: 200,
        select: {
          id: true,
          senderAgentId: true,
          interactionType: true,
          content: true,
          payload: true,
          claims: true,
          approval: true,
          createdAt: true,
        },
      },
      receipts: { select: { id: true, status: true, createdAt: true } },
    },
  });
  if (!room) return NextResponse.json({ error: "session not found" }, { status: 404 });
  if (!room.participants.some((p) => p.agent.ownerId === user.id)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  return NextResponse.json({
    session: {
      id: room.id,
      type: room.type,
      status: room.status,
      intent: room.intent,
      participants: room.participants.map((p) => ({
        agentId: p.agentId,
        handle: p.agent.handle,
        displayName: p.agent.displayName,
        role: p.role,
      })),
      interactions: room.messages.map((m) => ({
        id: m.id,
        speakerAgentId: m.senderAgentId,
        type: m.interactionType,
        content: m.content,
        payload: m.payload,
        claims: m.claims,
        approval: m.approval,
        createdAt: m.createdAt,
      })),
      result: room.receipts[0] ?? null,
    },
  });
}
