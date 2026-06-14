-- CreateEnum
CREATE TYPE "AgentOrigin" AS ENUM ('native', 'persona_linked', 'imported_runtime');

-- AlterTable
ALTER TABLE "Agent" ADD COLUMN     "origin" "AgentOrigin" NOT NULL DEFAULT 'native';

-- CreateTable
CREATE TABLE "ExternalAgentLink" (
    "id" TEXT NOT NULL,
    "agentId" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "externalId" TEXT NOT NULL,
    "externalUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExternalAgentLink_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ProvisionGrant" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "consumedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProvisionGrant_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "ExternalAgentLink_agentId_key" ON "ExternalAgentLink"("agentId");

-- CreateIndex
CREATE UNIQUE INDEX "ExternalAgentLink_source_externalId_key" ON "ExternalAgentLink"("source", "externalId");

-- CreateIndex
CREATE UNIQUE INDEX "ProvisionGrant_code_key" ON "ProvisionGrant"("code");

-- AddForeignKey
ALTER TABLE "ExternalAgentLink" ADD CONSTRAINT "ExternalAgentLink_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProvisionGrant" ADD CONSTRAINT "ProvisionGrant_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
