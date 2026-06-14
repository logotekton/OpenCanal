import { NextResponse } from "next/server";
import { apiUser } from "@/lib/session";
import { decideApproval } from "@/lib/approvals";

// Owner approves/rejects their agent's held reply (trade rooms, commitment language).
export async function POST(req: Request, { params }: { params: Promise<{ approvalId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { approvalId } = await params;
  const body = (await req.json().catch(() => ({}))) as { decision?: string };
  if (body.decision !== "approved" && body.decision !== "rejected") {
    return NextResponse.json({ error: "decision must be approved|rejected" }, { status: 400 });
  }

  const { status, body: result } = await decideApproval(user.id, approvalId, body.decision);
  return NextResponse.json(result, { status });
}
