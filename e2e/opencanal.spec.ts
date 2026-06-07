import { expect, test } from "@playwright/test";

test("main gateway opens into debate room", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/");
  await expect(page.getByRole("main", { name: "OpenCanal main gateway" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "OpenCanal" })).toBeVisible();

  await page.getByRole("textbox", { name: "Debate prompt" }).fill("OpenCanal은 왜 agent debate부터 시작해야 하나?");
  await page.getByRole("button", { name: "Open" }).click();
  await expect(page.getByText("agent 진입")).toBeVisible();
  await expect(page.getByRole("main", { name: "OpenCanal Debate Room" })).toBeVisible({ timeout: 7000 });

  await expect(page.locator(".debate-header p")).toHaveText("Agent Debate Room");
  await expect(page.getByText("Claim Stream")).toBeVisible();
  await expect(page.getByText("Debate Receipt")).toBeVisible();
  await expect(page.getByText(/fnv1a-/)).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
