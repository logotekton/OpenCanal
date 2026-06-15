import { timingSafeEqual } from "crypto";

// 텔레그램 브리지 워커 ↔ 플랫폼 내부 호출 인증. 게이트웨이와 동일한 패턴(공유 시크릿 + 상수시간 비교).
// 브리지 엔드포인트는 사용자 대리 동작(승인 등) 경로이므로 프로덕션에서 기본 시크릿은 거부한다.
const DEFAULT_SECRET = "dev-internal-secret";
const SECRET = process.env.BRIDGE_INTERNAL_SECRET ?? DEFAULT_SECRET;
const SECRET_BUF = Buffer.from(SECRET);
const INSECURE_IN_PROD = process.env.NODE_ENV === "production" && SECRET === DEFAULT_SECRET;

export function bridgeSecretOk(req: Request): boolean {
  if (INSECURE_IN_PROD) return false; // 프로덕션에서 기본 시크릿이면 전부 거부
  const provided = req.headers.get("x-bridge-secret");
  if (typeof provided !== "string") return false;
  const buf = Buffer.from(provided);
  if (buf.length !== SECRET_BUF.length) return false;
  return timingSafeEqual(buf, SECRET_BUF);
}
