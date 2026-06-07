# OpenCanal Motion Spec v0.1

## Primary Flow

Source: alt15 and alt25.

```text
Home idle
-> prompt submitted
-> personal agent interprets prompt
-> threshold seam appears
-> reasoning particles move toward agent
-> agent drifts toward threshold
-> Room preview becomes visible
-> Room entry action appears
```

## States

### 1. Home Idle

- Background: alt15 unknown abyss.
- One personal agent floats alone.
- Door/threshold is absent or nearly invisible.
- Prompt: `내 agent에게 무엇을 열어볼까요?`

### 2. Prompt Submitted

- Prompt text becomes visible as submitted text.
- Agent halo brightens.
- Small status chips appear: `의도 파악`, `근거 경로 탐색`, `Room 준비`.

### 3. Threshold Opening

- Door appears as a thin vertical seam, not a portal.
- It opens by widening light and mist, not by swinging or flashing.
- Keep the motion quiet and slow.

### 4. Agent Transit

- Agent drifts toward the seam.
- Reasoning particles move from prompt to agent to door.
- Movement should feel intentional, not game-like.

### 5. Room Ready

- Background crossfades toward alt25.
- Room beyond the door remains vague.
- `Room 입장` appears as a quiet glass action.

## Motion Timing

- Prompt to halo response: 300-600ms
- Reasoning particles: 900-1800ms
- Threshold seam: 1200-2200ms
- Agent drift: 1800-2800ms
- Room ready affordance: after 2300ms

## Interaction Rules

- The door should never look like a fantasy portal or quest gate.
- Avoid flashing effects, progress bars, XP-like affordances, and achievement language.
- The agent should feel awake, calm, and autonomous.
- The transition should preserve large negative space.
- The UI should remain user-facing, not administrative.

## Prototype

Local prototype:

`C:\Logotekton\OpenCanal\ui_prototype\index.html`
