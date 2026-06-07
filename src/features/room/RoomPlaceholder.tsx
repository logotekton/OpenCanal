import { AspectCanvas } from "../../components/harness/AspectCanvas";
import { TactileButton } from "../../components/harness/TactileButton";

type RoomPlaceholderProps = {
  question: string;
  onReturn: () => void;
};

export function RoomPlaceholder({ question, onReturn }: RoomPlaceholderProps) {
  return (
    <main className="room-placeholder-shell" aria-label="Debate Room preview">
      <AspectCanvas className="room-placeholder">
        <div className="room-placeholder__field">
          <span className="room-placeholder__agent room-placeholder__agent--a" />
          <span className="room-placeholder__agent room-placeholder__agent--b" />
          <span className="room-placeholder__agent room-placeholder__agent--c" />
          <span className="room-placeholder__agent room-placeholder__agent--d" />
          <div className="room-placeholder__question">
            <p>Debate Room 준비됨</p>
            <h2>{question}</h2>
          </div>
        </div>
        <TactileButton tone="quiet" className="room-placeholder__back" onClick={onReturn}>
          돌아가기
        </TactileButton>
      </AspectCanvas>
    </main>
  );
}
