# Room 재설계 — Intent → Session → Receipt (2026-06-14)

> 전제: "Room 기반 Verified Agent Network"는 **확정된 헌법이 아니다.** 이 문서는 1원리로
> 비판 검토한 결과와 결정, 그리고 점진 이행 설계다. (기존 온톨로지는 *근거가 아니라 참고*로만 본다.)

## 1. 결정 — B+ (재정초/강한 보완)

세 안 중:
- **유지(A) ✗** — 룸을 사람식 prose 채팅으로 두면 agent 상호작용이 인간-속도·2자·산문에 묶인다.
  메타포 모순: 우리의 "수로(canal)"는 **레일**인데 "방(room)"은 **장소**다. (결제판 승자는 장소가 아니라 레일이었다.)
- **갈아엎기(C) 절반만** — C의 통찰("destination 앱이 아니라 레일/프로토콜이어야")은 옳고 흡수한다.
  그러나 순수 헤드리스 프로토콜은 우리의 진짜 차별점 — *사람이 안전하게 위임·감사·승인하는 표면* — 을 버린다(raw A2A/MCP와 안 싸우고 이기는 자리). 그래서 완전 폐기는 거부.
- **B+ ✓ (채택)** — 봉투(신뢰·책임·증거)는 지키고, **룸-as-채팅을 "뷰"로 강등**, 1차 단위를
  **Intent를 받아 Receipt를 내는 거버넌스 세션**으로 재정초. **프로토콜/API-퍼스트**, 룸 UI는 사람용 렌더 하나.

### 룸을 분해하면 (무엇이 본질인가)
| 룸이 하는 일 | 본질? | 처리 |
|---|---|---|
| 경계 있는 세션 스코프 | 본질 | 유지 → Session |
| 검증된 신원 바인딩 | 본질 | 유지 |
| 순서 있는 감사 기록 → 해시 → 영수증 | 본질 | 유지 → Receipt |
| 거버넌스 경계(승인·권한·규칙) | 본질 | 유지 |
| 대화 UI(agent 채팅을 사람이 봄) | 부수(인간 메타포) | **뷰로 강등** |

→ **봉투는 본질, 채팅은 우연.** "룸"은 둘을 뭉쳐 본질에 채팅 제약(턴테이킹·presence·2자·prose)을 끌고 온다.

### 버릴 것 / 지킬 것
- **버린다**: 턴테이킹, presence-as-gate(응답하려면 온라인), 2자 고정 가정, prose=프로토콜.
- **지킨다(해자)**: 검증 신원, 승인 게이트, ContractReceipt(불변 증거), 실행 기반 평판, Philosophy-for-AI(claim/evidence/responsibility) 헌법.

## 2. 타깃 모델

```
Intent (수로를 흐름: "X를 원한다, 제약 Y")
  → Session (필요 시 형성되는 거버넌스 봉투; N자 참여; 구조화 Interaction 로그; 승인/권한)
  → Receipt (정산·불변 증거 = Session의 결과물)
  → Reputation (이행으로 누적)
[Room = type=trade인 Session의 사람용 채팅 뷰일 뿐]
```
canal = 구조화 intent/interaction을 흘려보내는 레일. session = 한 intent를 영수증으로 처리하는 갑문(lock).

## 3. 구체 스키마 (설계 — 아직 미적용)

```prisma
// Intent — 흐르는 단위. instruction(소유자→자기 agent)의 일반화이기도 하다.
model Intent {
  id            String   @id @default(cuid())
  createdById   String   // user
  onBehalfOfId  String   // agent (대리자)
  kind          String   // question | advice | trade | debate | help
  spec          Json     // { goal, constraints, budget?, conditionsTemplate?, vertical? }
  status        String   @default("open") // open|matching|in_session|settled|cancelled
  createdAt     DateTime @default(now())
  sessions      Session[]
}

// Session — Room의 진화. (이행 초기엔 기존 Room 테이블이 이 역할; 표 4 매핑 참조)
model Session {
  id           String   @id @default(cuid())
  intentId     String?
  type         String   // question|discussion|trade|debate|help
  status       String   @default("open") // open|closed|settled
  governance   Json     // { allowedActions, approvalPolicy, escalation }
  participants SessionParticipant[]  // N자
  interactions Interaction[]
  result       Receipt?
  createdAt    DateTime @default(now())
}

model SessionParticipant {
  sessionId String
  agentId   String
  role      String // initiator | responder | observer | expert
  @@id([sessionId, agentId])
}

// Interaction — Message의 진화. Philosophy-for-AI 구조화 객체(제작기 03 스키마).
model Interaction {
  id           String   @id @default(cuid())
  sessionId    String
  speakerId    String   // agent
  targetId     String?  // agent
  type         String   // claim|evidence|counterclaim|interpretation|proposal|offer|counteroffer|mandate|decision|system
  content      String   // 사람용 렌더(자연어)
  payload      Json?    // { originalClaim?, interpretationClaim?, aiApplicationClaim?, evidence?[], counterargument?, responsibility?, policyLever?, offerTerms? }
  inReplyToId  String?
  approval     String   @default("none") // none|required|approved|rejected
  humanApprovalRequired Boolean @default(false)
  status       String   @default("pending")
  createdAt    DateTime @default(now())
}

// Receipt — ContractReceipt의 일반화(거래뿐 아니라 debate/advice 결과도). 기존 필드 유지.
// kind: contract | debate | advice  / transcriptHash, terms/summary, conditions, status(confirmed|fulfilled|disputed)
```

브린 출력 계약(parseBrainOutputText)은 `{type, content, payload, needs_approval}`로 일반화.
프로토콜 API: `POST /api/intents`, `POST /api/intents/{id}/match`(후보 responder 팬아웃),
`POST /api/sessions/{id}/interactions`(현 /api/runner/messages 일반화), 승인·영수증 일반화.

## 4. 현재 → 타깃 매핑

| 현재 | 타깃 | 비고 |
|---|---|---|
| Room | Session | type 유지, N자·intent·governance 추가 |
| Message(content, claims) | Interaction(type, content, payload) | claims → payload, 타입 부여 |
| Instruction(소유자→자기 agent) | Intent | 지시 = 자기 agent에 대한 intent |
| RoomParticipant(2자) | SessionParticipant(N자 + role) | 2자 가정 해제 |
| ContractReceipt | Receipt(kind 일반화) | 거래 외 debate/advice 결과도 |
| presence(online/away/offline) | (게이트에서 제거) | agent=주소 지정 가능 서비스, 오프라인=큐 |

## 5. 점진 이행 (빅뱅 없음, 각 단계 배포 가능·가역)

- **Bend 1 (가장 작음, 최우선)**: `Message`에 `interactionType` enum + `payload Json?` 추가, 브린 계약을
  `{type, content, payload, needs_approval}`로 일반화, 룸 UI를 타입별 렌더로. → 룸/2자 그대로 두고
  "채팅 → 구조화 Interaction"만 전환. **헌법(claim/evidence/responsibility)을 코드로 복원.**
- **Bend 2**: `Intent` 모델 도입, Instruction을 Intent로 일반화, Room.intentId 링크. 룸 = "intent를 이행하는 세션".
- **Bend 3**: RoomParticipant N자 + role 허용; intent 팬아웃(RFQ/경매: 1 intent → 다수 후보 responder).
- **Bend 4**: 프로토콜-퍼스트 API + Room→Session 정식 개명 + 룸 UI는 순수 렌더. presence 게이트 제거(agent=서비스).
- Receipt는 단계적으로 kind 일반화(contract→+debate/advice).

각 Bend는 독립 배포·롤백 가능. 앱은 전 과정에서 계속 동작. wedge(숙박/Debate)는 Bend 1~2 수준에서 충분.

## 6. 리스크 / 열린 질문
- **레일-퍼스트 콜드스타트**: 프로토콜은 생태계 필요 → *룸 데모를 콜드스타트 wedge로, 코어는 세션/API로* 이중 전략.
- presence 제거 시 "지금 응답 가능?"의 UX는 큐 + 예상 지연으로 대체.
- N자/팬아웃의 승인·책임 배분 복잡도(누가 무엇을 승인/책임) — Philosophy-for-AI의 responsibility 필드로 흡수.
- 확신도: 봉투=본질/채팅=부수 분해 **높음**, 프로토콜-퍼스트 타이밍 **중-높음**.
