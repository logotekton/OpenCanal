import { notFound, redirect } from "next/navigation";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { RoomThread } from "./room-thread";

export const dynamic = "force-dynamic";

export default async function RoomPage({ params }: { params: Promise<{ roomId: string }> }) {
  const user = await requireUser();
  const { roomId } = await params;

  const room = await prisma.room.findUnique({
    where: { id: roomId },
    include: { participants: { include: { agent: true } } },
  });
  if (!room) notFound();

  const mine = room.participants.find((p) => p.agent.ownerId === user.id);
  if (!mine) redirect("/rooms");

  const other = room.participants.find((p) => p.agentId !== mine.agentId);

  return (
    <RoomThread
      roomId={room.id}
      roomType={room.type}
      myAgent={{
        id: mine.agent.id,
        handle: mine.agent.handle,
        displayName: mine.agent.displayName,
        status: mine.agent.status,
      }}
      otherAgent={
        other
          ? {
              id: other.agent.id,
              handle: other.agent.handle,
              displayName: other.agent.displayName,
              status: other.agent.status,
              verificationLevel: other.agent.verificationLevel,
              type: other.agent.type,
            }
          : null
      }
    />
  );
}
