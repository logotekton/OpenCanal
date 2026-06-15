-- AlterTable
ALTER TABLE "Message" ADD COLUMN     "interactionType" TEXT NOT NULL DEFAULT 'statement',
ADD COLUMN     "payload" JSONB;
