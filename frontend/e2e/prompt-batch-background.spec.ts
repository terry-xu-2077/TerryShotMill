import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("prompt batch returns to workspace once queued, without waiting or opening an editor", async ({ page }) => {
  const project = await createProject(page, "后台增强");
  await createTask(page, project.id, "增强任务");
  let batchPolls = 0;
  await page.route(`**/projects/${project.id}/prompt-enhancement-batches`, (route) => route.fulfill({
    json: { batchId: "pending-batch", state: "queued", items: [] },
  }));
  await page.route(`**/projects/${project.id}/prompt-enhancement-batches/pending-batch`, (route) => {
    batchPolls += 1;
    return route.fulfill({ json: { batchId: "pending-batch", state: "running", items: [] } });
  });
  await openProject(page, project.title);
  await page.getByText("#1 增强任务", { exact: true }).click({ modifiers: ["Control"] });
  await page.getByRole("region", { name: "批量操作" }).getByRole("button", { name: "AI 增强" }).click();
  await page.getByRole("button", { name: "开始增强" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "批量操作" })).toContainText("已选择 1 项");
  expect(batchPolls).toBe(0);
});

test("failed batch submission stays visible and can be retried", async ({ page }) => {
  const project = await createProject(page, "增强提交失败");
  await createTask(page, project.id, "增强任务");
  await page.route(`**/projects/${project.id}/prompt-enhancement-batches`, (route) => route.fulfill({
    status: 503, json: { detail: "unavailable" },
  }));
  await openProject(page, project.title);
  await page.getByText("#1 增强任务", { exact: true }).click({ modifiers: ["Control"] });
  await page.getByRole("region", { name: "批量操作" }).getByRole("button", { name: "AI 增强" }).click();
  await page.getByRole("button", { name: "开始增强" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("增强提交未确认");
  await expect(page.getByRole("button", { name: "开始增强" })).toBeEnabled();
});
