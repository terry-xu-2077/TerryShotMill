import { expect, test } from "@playwright/test";
import { createProject, createTask } from "./helpers";

test("home manages project archive, trash, restore and purge", async ({ page }) => {
  const project = await createProject(page, "项目生命周期");
  const task = await createTask(page, project.id, "原已删除任务");
  const activeTask = await createTask(page, project.id, "原正常任务");
  const archivedTask = await createTask(page, project.id, "原归档任务");
  expect((await page.request.post(`/api/v1/projects/${project.id}/tasks/lifecycle`, {
    data: { taskIds: [archivedTask.id], action: "archive" },
  })).ok()).toBeTruthy();
  expect((await page.request.post(`/api/v1/projects/${project.id}/tasks/lifecycle`, {
    data: { taskIds: [task.id], action: "trash" },
  })).ok()).toBeTruthy();
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "项目管理", exact: true }).click();
  const manager = page.getByRole("dialog", { name: "项目管理", exact: true });
  const row = manager.locator(".project-lifecycle-row").filter({ hasText: project.title });
  await row.getByRole("button", { name: "归档", exact: true }).click();
  const archive = page.getByRole("dialog", { name: "归档项目", exact: true });
  await archive.getByRole("button", { name: "归档项目", exact: true }).click();
  await expect(archive).toBeHidden();
  await expect(row).toHaveCount(0);
  await manager.getByRole("button", { name: "已归档", exact: true }).click();
  await row.getByRole("button", { name: "取消归档", exact: true }).click();
  const unarchive = page.getByRole("dialog", { name: "取消归档", exact: true });
  await unarchive.getByRole("button", { name: "取消归档", exact: true }).click();
  await expect(unarchive).toBeHidden();
  await expect(row).toHaveCount(0);
  await manager.getByRole("button", { name: "当前项目", exact: true }).click();
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "归档", exact: true }).click();
  await archive.getByRole("button", { name: "归档项目", exact: true }).click();
  await expect(archive).toBeHidden();
  await manager.getByRole("button", { name: "已归档", exact: true }).click();
  await row.getByRole("button", { name: "删除", exact: true }).click();
  const trash = page.getByRole("dialog", { name: "删除项目", exact: true });
  await trash.getByRole("button", { name: "删除项目", exact: true }).click();
  await expect(trash).toBeHidden();
  await manager.getByRole("button", { name: "回收站", exact: true }).click();
  await row.getByRole("button", { name: "恢复", exact: true }).click();
  const restore = page.getByRole("dialog", { name: "恢复项目", exact: true });
  await restore.getByRole("button", { name: "恢复项目", exact: true }).click();
  await expect(restore).toBeHidden();
  await manager.getByRole("button", { name: "已归档", exact: true }).click();
  await expect(row).toBeVisible();
  const workspace = await page.request.get(`/api/v1/projects/${project.id}/workspace?scope=trash`);
  expect((await workspace.json()).tasks.map((item: { id: string }) => item.id)).toContain(task.id);
  for (const [scope, expectedId] of [
    ["active", activeTask.id], ["archived", archivedTask.id], ["trash", task.id],
  ]) {
    const response = await page.request.get(`/api/v1/projects/${project.id}/workspace?scope=${scope}`);
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).tasks.map((item: { id: string }) => item.id)).toEqual([expectedId]);
  }
  await row.getByRole("button", { name: "删除", exact: true }).click();
  await trash.getByRole("button", { name: "删除项目", exact: true }).click();
  await expect(trash).toBeHidden();
  await manager.getByRole("button", { name: "回收站", exact: true }).click();
  await row.getByRole("button", { name: "永久删除", exact: true }).click();
  const purge = page.getByRole("dialog", { name: "永久删除项目", exact: true });
  await expect(purge.getByRole("checkbox", { name: "归档全部生成结果后删除" })).toBeChecked();
  await purge.getByRole("button", { name: "永久删除项目", exact: true }).click();
  await expect(purge).toBeHidden();
  await expect(row).toHaveCount(0);
});
