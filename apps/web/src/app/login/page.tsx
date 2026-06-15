import { devLoginEnabled, googleEnabled } from "@/auth";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <main className="flex min-h-[70vh] items-center justify-center px-6">
      <div className="card w-full max-w-md bg-canvas-soft">
        <p className="eyebrow mb-2">SIGN IN</p>
        <h1 className="display-md">OpenCanal 시작하기</h1>
        <LoginForm devLoginEnabled={devLoginEnabled} googleEnabled={googleEnabled} />
      </div>
    </main>
  );
}
