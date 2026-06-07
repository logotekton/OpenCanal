import { FormEvent, useEffect, useReducer, type CSSProperties } from "react";
import { AspectCanvas } from "../../components/harness/AspectCanvas";
import { ContrastContainer } from "../../components/harness/ContrastContainer";
import { TactileButton } from "../../components/harness/TactileButton";

type GatewayState =
  | "idle"
  | "prompt_submitted"
  | "interpreting"
  | "threshold_opening"
  | "agent_entering"
  | "room_requested";

type GatewayAction =
  | { type: "submit"; prompt: string }
  | { type: "advance"; state: GatewayState }
  | { type: "reset"; prompt: string };

type GatewayModel = {
  state: GatewayState;
  prompt: string;
};

const timing: Partial<Record<GatewayState, number>> = {
  prompt_submitted: 420,
  interpreting: 720,
  threshold_opening: 1250,
  agent_entering: 1750,
  room_requested: 850
};

const nextState: Partial<Record<GatewayState, GatewayState>> = {
  prompt_submitted: "interpreting",
  interpreting: "threshold_opening",
  threshold_opening: "agent_entering",
  agent_entering: "room_requested"
};

function gatewayReducer(model: GatewayModel, action: GatewayAction): GatewayModel {
  switch (action.type) {
    case "submit":
      return { state: "prompt_submitted", prompt: action.prompt };
    case "advance":
      return { ...model, state: action.state };
    case "reset":
      return { state: "idle", prompt: action.prompt };
  }
}

type MainGatewayProps = {
  initialPrompt: string;
  onPromptChange: (prompt: string) => void;
  onRoomRequested: () => void;
};

export function MainGateway({ initialPrompt, onPromptChange, onRoomRequested }: MainGatewayProps) {
  const [model, dispatch] = useReducer(gatewayReducer, {
    state: "idle",
    prompt: initialPrompt
  });

  useEffect(() => {
    if (model.state === "idle" || model.state === "room_requested") return;
    const followingState = nextState[model.state];
    if (!followingState) return;

    const timer = window.setTimeout(() => {
      dispatch({ type: "advance", state: followingState });
    }, timing[model.state]);

    return () => window.clearTimeout(timer);
  }, [model.state]);

  useEffect(() => {
    if (model.state !== "room_requested") return;
    const timer = window.setTimeout(onRoomRequested, timing.room_requested);
    return () => window.clearTimeout(timer);
  }, [model.state, onRoomRequested]);

  function submitPrompt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const prompt = String(formData.get("prompt") ?? "").trim() || initialPrompt;
    onPromptChange(prompt);
    dispatch({ type: "submit", prompt });
  }

  const active = model.state !== "idle";
  const opening = model.state === "threshold_opening" || model.state === "agent_entering" || model.state === "room_requested";
  const entering = model.state === "agent_entering" || model.state === "room_requested";

  return (
    <main className="gateway-shell" aria-label="OpenCanal main gateway">
      <AspectCanvas className="gateway-canvas">
        <ContrastContainer fallbackColor="#061018" className="gateway-scene">
          <div className="gateway-world" aria-hidden="true">
            <span className="gateway-world__light" />
            <span className="gateway-world__ridge gateway-world__ridge--left" />
            <span className="gateway-world__ridge gateway-world__ridge--right" />
            <span className="gateway-world__path" />
          </div>
          <div className={`gateway-orbit ${active ? "is-awake" : ""} ${opening ? "is-opening" : ""} ${entering ? "is-entering" : ""}`}>
            <div className="abyss-grain" aria-hidden="true" />
            <div className="threshold-field" aria-hidden="true">
              <div className="threshold-field__seam" />
              <div className="threshold-field__mist" />
            </div>
            <div className="reasoning-path" aria-hidden="true">
              {Array.from({ length: 9 }).map((_, index) => (
                <span key={index} style={{ "--particle-index": index } as CSSProperties} />
              ))}
            </div>
            <div className="personal-agent" aria-label="personal agent">
              <span className="personal-agent__core" />
              <span className="personal-agent__halo" />
              <span className="personal-agent__sigil" />
            </div>
          </div>

          <section className="gateway-brand" aria-label="OpenCanal">
            <p>Verified Agent Platform</p>
            <h1>OpenCanal</h1>
          </section>

          <div className="agent-caption" aria-hidden="true">
            <strong>나의 Agent</strong>
            <span>Verified</span>
          </div>

          <div className="mandate-trail" aria-hidden="true">
            <span />
            위임 경로
            <em>Mandate Trail</em>
          </div>

          <form className={`prompt-dock ${active ? "is-submitted" : ""}`} onSubmit={submitPrompt}>
            <span className="prompt-dock__orb" aria-hidden="true" />
            <input
              aria-label="Debate prompt"
              name="prompt"
              disabled={active}
              placeholder="내 agent에게 무엇을 열어볼까요?"
            />
            <TactileButton tone="glass" type="submit" disabled={active}>
              {active ? "Opening" : "Open"}
            </TactileButton>
          </form>

          <nav className="gateway-actions" aria-label="Gateway actions">
            <button type="button">방향 정하기</button>
            <button type="button">기억 보기</button>
            <button type="button">Room 열기</button>
          </nav>

          <div className={`gateway-status ${active ? "is-visible" : ""}`} aria-live="polite">
            <span className={model.state === "prompt_submitted" ? "is-active" : ""}>의도 파악</span>
            <span className={model.state === "interpreting" || opening ? "is-active" : ""}>토론 Room 준비</span>
            <span className={entering ? "is-active" : ""}>agent 진입</span>
          </div>

          <div className={`room-signal ${model.state === "room_requested" ? "is-visible" : ""}`}>
            Debate Room
          </div>
        </ContrastContainer>
      </AspectCanvas>
    </main>
  );
}
