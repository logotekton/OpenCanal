// 멀티룸 병렬 처리: 같은 룸은 FIFO 순차(대화 순서 보장), 룸 간에는 워커 풀 병렬.
// 전역 시간당 캡으로 사용자 본인의 구독 쿼터를 보호한다.

export class RoomQueue {
  private queues = new Map<string, (() => Promise<void>)[]>();
  private active = new Set<string>(); // roomIds currently being processed
  private running = 0;
  private replyTimestamps: number[] = [];

  constructor(
    private concurrency: number,
    private repliesPerHour: number
  ) {}

  get busy(): boolean {
    return this.running > 0;
  }

  private capReached(): boolean {
    const hourAgo = Date.now() - 3600_000;
    this.replyTimestamps = this.replyTimestamps.filter((t) => t > hourAgo);
    return this.replyTimestamps.length >= this.repliesPerHour;
  }

  recordReply(): void {
    this.replyTimestamps.push(Date.now());
  }

  enqueue(roomId: string, job: () => Promise<void>): void {
    if (this.capReached()) {
      console.warn(`[queue] hourly reply cap (${this.repliesPerHour}) reached — dropping job for room ${roomId}; it stays pending and drains later`);
      return;
    }
    const q = this.queues.get(roomId) ?? [];
    q.push(job);
    this.queues.set(roomId, q);
    this.pump();
  }

  private pump(): void {
    if (this.running >= this.concurrency) return;
    // Pick the next room that has work and isn't already being processed
    for (const [roomId, jobs] of this.queues) {
      if (this.active.has(roomId) || jobs.length === 0) continue;
      const job = jobs.shift()!;
      if (jobs.length === 0) this.queues.delete(roomId);
      this.active.add(roomId);
      this.running++;
      job()
        .catch((err) => console.error(`[queue] job failed (room ${roomId}):`, err))
        .finally(() => {
          this.active.delete(roomId);
          this.running--;
          this.pump();
        });
      if (this.running >= this.concurrency) return;
    }
  }
}
