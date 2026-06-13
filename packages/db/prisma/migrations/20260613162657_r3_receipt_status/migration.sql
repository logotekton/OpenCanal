-- CreateEnum
CREATE TYPE "ReceiptStatus" AS ENUM ('confirmed', 'fulfilled', 'disputed');

-- AlterTable
ALTER TABLE "ContractReceipt" ADD COLUMN     "disputedAt" TIMESTAMP(3),
ADD COLUMN     "fulfilledAt" TIMESTAMP(3),
ADD COLUMN     "note" TEXT,
ADD COLUMN     "status" "ReceiptStatus" NOT NULL DEFAULT 'confirmed';
