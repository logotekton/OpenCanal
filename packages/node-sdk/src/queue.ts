// 멀티룸 병렬 처리: 같은 룸은 FIFO 순차(대화 순서 보장), 룸 간에는 워커 풀 병렬.
// 전역 시간당 캡으로 호스트 런타임의 구독 쿼터(LLM 호출)를 보호한다.
// 러너·외부 어댑터 공통 — OpenCanalNode가 사용한다.

export class RoomQueue {
  private queues = new Map<string, (() => Promise<void>)[]>();
  private active = new Set<string>(); // roomIds currently being processed
  private running = 0;
  private replyTimestamps: number[] = [];

  constructor(
    private concurrency: number,
    private repliesPerHour: number,
    private log: (msg: string) => void = () => {}
  ) {}

  get busy(): boolean {
    return this.running > 0;
  }

  // 시간당 캡까지 남은 대기 시간(ms). 0이면 여유 있음.
  private capWaitMs(): number {
    const hourAgo = Date.now() - 3600_000;
    this.replyTimestamps = this.replyTimestamps.filter((t) => t > hourAgo);
    if (this.replyTimestamps.length < this.repliesPerHour) return 0;
    const oldest = this.replyTimestamps[0];
    return Math.max(0, oldest + 3600_000 - Date.now());
  }

  recordReply(): void {
    this.replyTimestamps.push(Date.now());
  }

  enqueue(roomId: string, job: () => Promise<void>): void {
    const wait = this.capWaitMs();
    if (wait > 0) {
      // 캡 도달: 드롭하지 않고 여유가 생길 때까지 미뤘다 재시도 (작업 유실 방지)
      this.log(
        `[queue] hourly reply cap (${this.repliesPerHour}) reached — deferring room ${roomId} by ${Math.ceil(wait / 1000)}s`
      );
      setTimeout(() => this.enqueue(roomId, job), wait + 100);
      return;
    }
    const q = this.queues.get(roomId) ?? [];
    q.push(job);
    this.queues.set(roomId, q);
    this.pump();
  }

  private pump(): void {
    if (this.running >= this.concurrency) return;
    // 작업이 있고 아직 처리 중이 아닌 다음 룸을 고른다
    for (const [roomId, jobs] of this.queues) {
      if (this.active.has(roomId) || jobs.length === 0) continue;
      const job = jobs.shift()!;
      if (jobs.length === 0) this.queues.delete(roomId);
      this.active.add(roomId);
      this.running++;
      job()
        .catch((err) => this.log(`[queue] job failed (room ${roomId}): ${err}`))
        .finally(() => {
          this.active.delete(roomId);
          this.running--;
          this.pump();
        });
      if (this.running >= this.concurrency) return;
    }
  }
}
