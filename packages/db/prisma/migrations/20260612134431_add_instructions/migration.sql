-- CreateEnum
CREATE TYPE "InstructionStatus" AS ENUM ('pending', 'processed', 'failed');

-- CreateTable
CREATE TABLE "Instruction" (
    "id" TEXT NOT NULL,
    "roomId" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "status" "InstructionStatus" NOT NULL DEFAULT 'pending',
    "resultMessageId" TEXT,
    "error" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processedAt" TIMESTAMP(3),

    CONSTRAINT "Instruction_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Instruction_agentId_status_idx" ON "Instruction"("agentId", "status");

-- CreateIndex
CREATE INDEX "Instruction_roomId_createdAt_idx" ON "Instruction"("roomId", "createdAt");

-- AddForeignKey
ALTER TABLE "Instruction" ADD CONSTRAINT "Instruction_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "Room"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Instruction" ADD CONSTRAINT "Instruction_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;
