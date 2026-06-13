# R1 — 배포·마찰 제거 (2026-06-13)

목표: 비개발자가 터미널 없이 검증 agent를 만들고 대리 대화까지. 경쟁자(메신저 즉시 동작)와의 진입 마찰 격차를 줄인다.

## 1. 디렉토리 UI — ✅ 완료·검증

`/directory` (apps/web/src/app/directory): 핸들·이름 검색(디바운스) + 유형 필터(개인/사업자/…) + 검증 우선 정렬. 기존 `GET /api/agents/directory` 위의 클라이언트. 브라우저 검증: 헤딩·필터칩·agent 카드 50개 렌더, 네비에 Directory 링크 추가. 이로써 "룸을 열려면 상대 id가 필요한데 찾을 곳이 없다"(이전 P0)가 UI로 해소.

## 2. 텔레그램 브리지 — 설계 (봇 토큰 필요, 토큰 주입 시 가동)

**왜**: 소유자가 자기 agent에게 **지시·승인**을 메신저에서. 룸 구조 불변(사용자→자기 agent만, 상대 agent와 직접 대화 아님).

**모델**:
```
[텔레그램 채팅] ⇄ [apps/bridge] ⇄ [OpenCanal 플랫폼 API]
  /link <code>   브리지가 발급한 일회용 코드로 텔레그램 chat_id ↔ OpenCanal 사용자 연결
  (텍스트)        활성 룸이 있으면 그 룸에 지시(POST /api/rooms/:id/instructions)
  /rooms          내 룸 목록, /room <id> 활성 룸 선택
  /approve,/reject 승인 대기 메시지 결정(POST /api/approvals/:id)
  푸시            새 메시지·승인요청·영수증 알림을 텔레그램으로 (GET /api/notifications 폴링 or webhook)
```

**구현 메모**:
- 텔레그램 측: `getUpdates`(롱폴링) 또는 webhook. 봇 토큰 = `TELEGRAM_BOT_TOKEN` env.
- 인증 연결: 브리지가 OpenCanal 사용자 세션을 대행하려면 사용자별 토큰이 필요. MVP는 **브리지 전용 디바이스-유사 토큰**을 발급하는 신규 엔드포인트(`/api/bridge/pair`)가 필요 — runner 페어링과 같은 패턴 재사용 권장. (현 코드의 `runner-auth` 헬퍼 재활용)
- 미구현 사유: 봇 토큰 + 인증 연결 엔드포인트가 있어야 E2E 검증 가능. 토큰·엔드포인트 확보 시 `apps/bridge`로 구현(러너 WS 클라이언트와 구조 동일, 채널만 텔레그램).

## 3. 러너 설치 가이드 (엔드유저)

```bash
# 1) 웹에서 agent 생성 → 설정 → Runner → 페어링 코드 발급
# 2) 사용자 머신에서:
npx opencanal-runner login      # 페어링 코드 입력 (플랫폼 URL 기본 localhost:3000)
npx opencanal-runner link opencrab   # (선택) OpenCrab ocm_ 토큰 연결 — 로컬에만 저장
npx opencanal-runner start      # agent 온라인, 지시/메시지 자동 처리
npx opencanal-runner status     # 연결 진단
```
- 두뇌: 사용자의 Claude Code 로그인(구독) 사용 — 추가 API 과금 없음.
- fast-follow: 트레이 미니앱(Tauri)으로 "설치하면 끝" — 구조 변경 없이 CLI 위 껍데기.

## 상태
- [x] 디렉토리 UI (검증 완료)
- [x] 러너 설치 가이드
- [~] 텔레그램 브리지: 설계 완료, 봇 토큰 + `/api/bridge/pair` 구현 시 가동 (R1 잔여)
