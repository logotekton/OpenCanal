-- CreateEnum
CREATE TYPE "NightRunStatus" AS ENUM ('running', 'completed', 'failed');

-- CreateEnum
CREATE TYPE "NightTaskStatus" AS ENUM ('queued', 'running', 'produced', 'skipped', 'failed');

-- CreateEnum
CREATE TYPE "ReviewState" AS ENUM ('pending', 'approved', 'rejected');

-- CreateTable
CREATE TABLE "NightPolicy" (
    "id" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "kind" TEXT NOT NULL DEFAULT 'decision',
    "text" TEXT NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NightPolicy_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NightDirective" (
    "id" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NightDirective_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NightTask" (
    "id" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "runId" TEXT,
    "title" TEXT NOT NULL,
    "brief" TEXT NOT NULL,
    "originPolicyId" TEXT,
    "originNote" TEXT,
    "status" "NightTaskStatus" NOT NULL DEFAULT 'queued',
    "order" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NightTask_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NightRun" (
    "id" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "status" "NightRunStatus" NOT NULL DEFAULT 'running',
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),
    "error" TEXT,
    "journal" JSONB NOT NULL DEFAULT '[]',

    CONSTRAINT "NightRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NightArtifact" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "taskId" TEXT,
    "agentId" TEXT NOT NULL,
    "kind" TEXT NOT NULL DEFAULT 'markdown',
    "title" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "review" "ReviewState" NOT NULL DEFAULT 'pending',
    "reviewReason" TEXT,
    "reviewedById" TEXT,
    "reviewedAt" TIMESTAMP(3),
    "correctionIngestedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NightArtifact_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "NightPolicy_agentId_active_idx" ON "NightPolicy"("agentId", "active");

-- CreateIndex
CREATE INDEX "NightDirective_agentId_active_idx" ON "NightDirective"("agentId", "active");

-- CreateIndex
CREATE INDEX "NightTask_agentId_status_order_idx" ON "NightTask"("agentId", "status", "order");

-- CreateIndex
CREATE INDEX "NightRun_agentId_startedAt_idx" ON "NightRun"("agentId", "startedAt");

-- CreateIndex
CREATE INDEX "NightArtifact_agentId_review_idx" ON "NightArtifact"("agentId", "review");

-- CreateIndex
CREATE INDEX "NightArtifact_runId_idx" ON "NightArtifact"("runId");

-- AddForeignKey
ALTER TABLE "NightPolicy" ADD CONSTRAINT "NightPolicy_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightDirective" ADD CONSTRAINT "NightDirective_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightTask" ADD CONSTRAINT "NightTask_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightTask" ADD CONSTRAINT "NightTask_runId_fkey" FOREIGN KEY ("runId") REFERENCES "NightRun"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightRun" ADD CONSTRAINT "NightRun_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightArtifact" ADD CONSTRAINT "NightArtifact_runId_fkey" FOREIGN KEY ("runId") REFERENCES "NightRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightArtifact" ADD CONSTRAINT "NightArtifact_taskId_fkey" FOREIGN KEY ("taskId") REFERENCES "NightTask"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightArtifact" ADD CONSTRAINT "NightArtifact_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NightArtifact" ADD CONSTRAINT "NightArtifact_reviewedById_fkey" FOREIGN KEY ("reviewedById") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

