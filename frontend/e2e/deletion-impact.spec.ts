import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject, selectAllTasks } from "./helpers";

test("deletion shows external impacts once, trash uses a tooltip, purge leaves missing-source warning", async ({ page }) => {
  const project = await createProject(page, "引用删除验收");
  const source = await createTask(page, project.id, "来源任务");
  const submitted = await page.request.post(`/api/v1/projects/${project.id}/tasks/${source.id}/generation`, { data: {} });
  expect(submitted.ok()).toBeTruthy();
  const job = await submitted.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  const created = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: { title: "承接任务", userPrompt: "延续上一镜头", generation: { contextMode: "尾帧承接" } },
  });
  expect(created.ok()).toBeTruthy();
  const target = await created.json();
  await openProject(page, project.title);
  await selectAllTasks(page);
  const actions = page.getByRole("region", { name: "任务操作", exact: true });
  await actions.getByRole("button", { name: "删除", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "删除任务", exact: true });
  await expect(confirm.getByRole("button", { name: "删除任务", exact: true })).toBeEnabled();
  await expect(confirm.getByRole("region", { name: "受影响任务" })).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await confirm.getByRole("button", { name: "取消", exact: true }).click();
  await expect(confirm).toBeHidden();
  await page.locator("label").filter({ has: page.getByRole("checkbox", { name: "选择任务 · 承接任务", exact: true }) }).click();
  await actions.getByRole("button", { name: "删除", exact: true }).click();
  await expect(confirm.getByRole("region", { name: "受影响任务" })).toContainText("承接任务：画面承接来源“来源任务”将移入回收站");
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await confirm.getByRole("button", { name: "删除任务", exact: true }).click();
  await expect(confirm).toBeHidden();
  await page.getByRole("button", { name: "已归档", exact: true }).click();
  const browser = page.getByRole("dialog", { name: "任务归档与回收站", exact: true });
  await browser.getByRole("button", { name: "回收站", exact: true }).click();
  const sourceRow = browser.locator(".task-lifecycle-row").filter({ hasText: "来源任务" });
  const warning = sourceRow.getByRole("button", { name: "查看引用警告", exact: true });
  await warning.hover();
  await expect(page.getByRole("tooltip")).toContainText("承接任务");
  await warning.click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await browser.getByRole("heading", { name: "任务归档与回收站" }).click();
  await sourceRow.locator("label").filter({ has: page.getByRole("checkbox", { name: "选择任务 · 来源任务", exact: true }) }).click();
  await browser.getByRole("button", { name: "永久删除", exact: true }).click();
  const purge = page.getByRole("dialog", { name: "永久删除任务", exact: true });
  await expect(purge.getByRole("region", { name: "受影响任务" })).toContainText("将永久丢失");
  await purge.getByRole("button", { name: "永久删除任务", exact: true }).click();
  await expect(purge).toBeHidden();
  await expect(browser.getByText("这里没有任务。")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(browser).toBeHidden();
  const targetRow = page.locator(".task-collection-item").filter({ hasText: "承接任务" });
  await targetRow.getByRole("button", { name: "查看引用警告", exact: true }).hover();
  await expect(page.getByRole("tooltip")).toContainText("删除");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const workspace = await (await page.request.get(`/api/v1/projects/${project.id}/workspace`)).json();
  expect(workspace.tasks.find((item: { id: string }) => item.id === target.id).missingReferences).toEqual([
    expect.objectContaining({ sourceTaskId: source.id, sourceTaskTitle: "来源任务", kind: "visual" }),
  ]);
});
