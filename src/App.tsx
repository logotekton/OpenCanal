import { useMemo, useState } from "react";
import { DebateRoomView } from "./features/debate/DebateRoom";
import { MainGateway } from "./features/gateway/MainGateway";

type AppView = "gateway" | "room";

export default function App() {
  const [view, setView] = useState<AppView>("gateway");
  const [debateQuestion, setDebateQuestion] = useState("OpenCanal의 첫 Room을 열어줘");

  const roomTitle = useMemo(() => {
    return debateQuestion.trim() || "OpenCanal의 첫 Room을 열어줘";
  }, [debateQuestion]);

  if (view === "room") {
    return <DebateRoomView question={roomTitle} onReturn={() => setView("gateway")} />;
  }

  return (
    <MainGateway
      initialPrompt={roomTitle}
      onPromptChange={setDebateQuestion}
      onRoomRequested={() => setView("room")}
    />
  );
}
