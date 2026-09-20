import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("configured workflow choice survives save, reload, and reopening the task", async ({ page }) => {
  const original = await (await page.request.get("/api/v1/application/settings")).json();
  const profiles = [
    { id: "standard", name: "标准视频", resolution: "720p", quality: "标准", workflowFile: "standard.json", enabled: true },
    { id: "detail", name: "精细视频", resolution: "1080p", quality: "高质量", workflowFile: "detail.json", enabled: true },
  ];
  try {
    const configured = await page.request.patch("/api/v1/application/settings", { data: {
      ...original, comfyui: { ...original.comfyui, defaultProfileId: "standard", workflowProfiles: profiles },
    } });
    expect(configured.ok()).toBeTruthy();
    const project = await createProject(page, "工作流选择");
    const task = await createTask(page, project.id);
    await openProject(page, project.title);
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    await page.getByRole("button", { name: "生成参数", exact: true }).click();
    await expect(page.getByRole("tablist", { name: "分辨率" })).toHaveCount(0);
    await expect(page.getByRole("tablist", { name: "质量档位" })).toHaveCount(0);
    await page.getByRole("combobox", { name: "生成工作流" }).click();
    await page.getByRole("option", { name: "精细视频", exact: true }).click();
    const saved = page.waitForResponse((response) => response.url().endsWith(`/tasks/${task.id}`) && response.request().method() === "PATCH");
    await page.getByRole("button", { name: "保存", exact: true }).click();
    expect((await saved).ok()).toBeTruthy();
    const editor = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${task.id}/editor`)).json();
    expect(editor.generation.workflowProfileId).toBe("detail");
    await openProject(page, project.title);
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    await page.getByRole("button", { name: "生成参数", exact: true }).click();
    await expect(page.getByRole("combobox", { name: "生成工作流" })).toContainText("精细视频");
    await expect(page.getByRole("slider", { name: "总秒数" })).toBeVisible();
  } finally {
    await page.request.patch("/api/v1/application/settings", { data: original });
  }
});
