import { useMemo, useState } from "react";
import { MainGateway } from "./features/gateway/MainGateway";
import { RoomPlaceholder } from "./features/room/RoomPlaceholder";

type AppView = "gateway" | "room";

export default function App() {
  const [view, setView] = useState<AppView>("gateway");
  const [debateQuestion, setDebateQuestion] = useState("OpenCanal의 첫 Room을 열어줘");

  const roomTitle = useMemo(() => {
    return debateQuestion.trim() || "OpenCanal의 첫 Room을 열어줘";
  }, [debateQuestion]);

  if (view === "room") {
    return <RoomPlaceholder question={roomTitle} onReturn={() => setView("gateway")} />;
  }

  return (
    <MainGateway
      initialPrompt={roomTitle}
      onPromptChange={setDebateQuestion}
      onRoomRequested={() => setView("room")}
    />
  );
}
