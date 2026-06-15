-- CreateTable
CREATE TABLE "AgentCapability" (
    "id" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "description" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "requiresApproval" BOOLEAN NOT NULL DEFAULT true,
    "source" TEXT NOT NULL DEFAULT 'manual',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "AgentCapability_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "AgentCapability_agentId_idx" ON "AgentCapability"("agentId");

-- CreateIndex
CREATE UNIQUE INDEX "AgentCapability_agentId_key_key" ON "AgentCapability"("agentId", "key");

-- AddForeignKey
ALTER TABLE "AgentCapability" ADD CONSTRAINT "AgentCapability_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;
