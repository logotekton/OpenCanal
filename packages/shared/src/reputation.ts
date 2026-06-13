// 평판 v1 — 자기소개가 아니라 실행 결과로 신뢰도를 계산한다 (v1 Reputation Pack).
// 순수 함수: DB 집계(web/lib/reputation.ts)와 분리해 테스트·재사용 가능하게 둔다.
// v0(프로필 인라인: 메시지수/승인률/거래수)를 응답률·이행률·분쟁률·근거점수로 확장한다.

export interface ReputationInput {
  // 응답률: 이 agent에게 전달된 상대 메시지 중 agent가 응답(answered)한 비율
  incomingTotal: number;
  incomingAnswered: number;
  // 승인률/반려율: 소유자 결정이 끝난(approved|rejected) 승인 요청
  approvalsDecided: number;
  approvalsApproved: number;
  // 이행률/분쟁률: 이 agent가 당사자인 확정 영수증의 생애주기
  receiptsTotal: number;
  receiptsFulfilled: number;
  receiptsDisputed: number;
  // 근거점수: agent가 보낸 메시지 중 evidence/responsibility claim을 단 비율
  messagesSent: number; // 전체(표시용)
  evidenceConsidered: number; // 근거점수 분모(샘플 크기)
  messagesWithEvidence: number; // 근거점수 분자
}

export interface ReputationV1 {
  responseRate: number | null; // 0..100, 표본 없으면 null
  approvalRate: number | null;
  rejectionRate: number | null;
  fulfillmentRate: number | null;
  disputeRate: number | null;
  evidenceScore: number | null;
  transactionCount: number; // 확정 영수증 수
  messagesSent: number;
  trustScore: number | null; // 가용 신호 가중 합성 0..100
  sampleSize: number; // 신뢰도 판단용 총 상호작용 표본
}

/** den>0일 때만 백분율(0..100), 아니면 null(표본 없음 → "—"로 표시). */
function pct(num: number, den: number): number | null {
  if (den <= 0) return null;
  return Math.round((num / den) * 100);
}

/**
 * 실행 데이터 집계를 평판 v1 지표로 환산한다.
 * trustScore는 데이터가 있는 신호만 가중 평균하고 가중치를 재정규화한다 —
 * 거래 이력이 없는 신생 agent가 분쟁률 0%로 만점을 받는 왜곡을 피한다.
 */
export function computeReputationV1(input: ReputationInput): ReputationV1 {
  const responseRate = pct(input.incomingAnswered, input.incomingTotal);
  const approvalRate = pct(input.approvalsApproved, input.approvalsDecided);
  const rejectionRate = pct(
    input.approvalsDecided - input.approvalsApproved,
    input.approvalsDecided
  );
  const fulfillmentRate = pct(input.receiptsFulfilled, input.receiptsTotal);
  const disputeRate = pct(input.receiptsDisputed, input.receiptsTotal);
  const evidenceScore = pct(input.messagesWithEvidence, input.evidenceConsidered);

  // 가용 신호만 가중 합성 (분쟁률은 낮을수록 좋으므로 100-disputeRate로 반영)
  const components: { value: number; weight: number }[] = [];
  if (responseRate !== null) components.push({ value: responseRate, weight: 0.2 });
  if (approvalRate !== null) components.push({ value: approvalRate, weight: 0.25 });
  if (fulfillmentRate !== null) components.push({ value: fulfillmentRate, weight: 0.3 });
  if (disputeRate !== null) components.push({ value: 100 - disputeRate, weight: 0.15 });
  if (evidenceScore !== null) components.push({ value: evidenceScore, weight: 0.1 });

  let trustScore: number | null = null;
  if (components.length > 0) {
    const totalWeight = components.reduce((s, c) => s + c.weight, 0);
    trustScore = Math.round(
      components.reduce((s, c) => s + c.value * c.weight, 0) / totalWeight
    );
  }

  return {
    responseRate,
    approvalRate,
    rejectionRate,
    fulfillmentRate,
    disputeRate,
    evidenceScore,
    transactionCount: input.receiptsTotal,
    messagesSent: input.messagesSent,
    trustScore,
    sampleSize: input.incomingTotal + input.approvalsDecided + input.receiptsTotal,
  };
}
