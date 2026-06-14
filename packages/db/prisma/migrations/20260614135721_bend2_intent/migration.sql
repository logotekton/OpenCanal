-- AlterTable
ALTER TABLE "Room" ADD COLUMN     "intentId" TEXT;

-- CreateTable
CREATE TABLE "Intent" (
    "id" TEXT NOT NULL,
    "createdById" TEXT NOT NULL,
    "onBehalfOfId" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "spec" JSONB NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'open',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Intent_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Intent_createdById_idx" ON "Intent"("createdById");

-- CreateIndex
CREATE INDEX "Intent_onBehalfOfId_status_idx" ON "Intent"("onBehalfOfId", "status");

-- CreateIndex
CREATE INDEX "Room_intentId_idx" ON "Room"("intentId");

-- AddForeignKey
ALTER TABLE "Intent" ADD CONSTRAINT "Intent_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Intent" ADD CONSTRAINT "Intent_onBehalfOfId_fkey" FOREIGN KEY ("onBehalfOfId") REFERENCES "Agent"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Room" ADD CONSTRAINT "Room_intentId_fkey" FOREIGN KEY ("intentId") REFERENCES "Intent"("id") ON DELETE SET NULL ON UPDATE CASCADE;
