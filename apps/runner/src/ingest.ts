import type { PlatformApi } from "./api";
import type { OpencrabClient } from "./sources/opencrab";

// 거래 영수증을 OpenCrab(학습 메모리)에 ingest한다 (R3). ocm_ 없으면 no-op.
// 같은 영수증이라도 상태가 바뀌면(confirmed→fulfilled→disputed) 다시 ingest.
// OpenCanalNode의 onConnect 훅에서 (재)연결마다 호출된다.
export class ReceiptIngester {
  private done = new Map<string, string>();

  constructor(
    private api: PlatformApi,
    private opencrab: OpencrabClient | null
  ) {}

  async run(): Promise<number> {
    if (!this.opencrab) return 0;
    const { receipts } = await this.api.receipts().catch(() => ({ receipts: [] }));
    let count = 0;
    for (const r of receipts) {
      if (this.done.get(r.id) === r.status) continue;
      if (await this.opencrab.ingestReceipt(r)) {
        this.done.set(r.id, r.status);
        count++;
      }
    }
    if (count > 0) console.log(`[runner] OpenCrab에 거래 이력 ${count}건 ingest`);
    return count;
  }
}
