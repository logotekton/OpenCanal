-- DropForeignKey
ALTER TABLE "ContractReceipt" DROP CONSTRAINT "ContractReceipt_proposalMessageId_fkey";

-- DropForeignKey
ALTER TABLE "ContractReceipt" DROP CONSTRAINT "ContractReceipt_roomId_fkey";

-- CreateIndex
CREATE INDEX "Message_roomId_status_createdAt_idx" ON "Message"("roomId", "status", "createdAt");

-- AddForeignKey
ALTER TABLE "ContractReceipt" ADD CONSTRAINT "ContractReceipt_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "Room"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ContractReceipt" ADD CONSTRAINT "ContractReceipt_proposalMessageId_fkey" FOREIGN KEY ("proposalMessageId") REFERENCES "Message"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
