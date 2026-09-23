import { expect, test } from "@playwright/test";

import { createProject, importImage, openProject, useTextPrompt } from "./helpers";

test("new task draft can enhance a prompt without being persisted on Cancel", async ({ page }) => {
  const project = await createProject(page, "草稿增强");
  await openProject(page, project.title);
  await page.getByRole("button", { name: "新建任务" }).click();
  await useTextPrompt(page, "角色在雨夜码头回头看向镜头。");

  await page.getByRole("tab", { name: /AI 增强/ }).click();
  await page.getByTestId("simple-task-editor").getByRole("button", { name: "增强", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "AI 增强提示词可视化" })).toContainText("角色在雨夜码头回头看向镜头");
  await page.getByRole("button", { name: "取消" }).click();

  await expect(page.getByRole("region", { name: "任务区域" })).toContainText("0 个任务");
  const workspace = await page.request.get(`/api/v1/projects/${project.id}/workspace`);
  expect((await workspace.json()).tasks).toHaveLength(0);
});

test("H3 @ asset menu inserts a readable reference and Save binds that asset", async ({ page }) => {
  const settings = await (await page.request.get("/api/v1/application/settings")).json();
  await page.route("**/api/v1/comfyui/workflows", (route) => route.fulfill({ json: [{
    id: "slots.json", relativePath: "slots.json", fileName: "slots.json", name: "Slots", format: "canvas", executable: true, hasShotmillBridge: true, warnings: [], outputs: [],
    inputs: [0, 1, 2].map((index) => ({ name: `图片 ${index + 1}`, type: "IMAGE", direction: "input", targetNodeId: "9", targetPort: `ref_image_${index}` })),
  }] }));
  await page.request.patch("/api/v1/application/settings", { data: { ...settings, comfyui: { ...settings.comfyui, defaultProfileId: "slots", workflowProfiles: [{ id: "slots", name: "输入槽位", enabled: true, resolution: "720p", quality: "标准", workflowFile: "slots.json" }] } } });
  try {
  const project = await createProject(page, "资产引用");
  const asset = await importImage(page, project.id);
  await openProject(page, project.title);
  await page.getByRole("button", { name: "新建任务" }).click();

  const prompt = await useTextPrompt(page, "镜头参考 @林澜");
  await expect(page.getByRole("listbox", { name: "引用任务资产" }).getByRole("option")).toHaveCount(0);
  await prompt.press("Escape");
  await page.getByRole("button", { name: /图片 3 · ref_image_2/ }).click();
  await page.getByRole("button", { name: "填入 林澜主视觉" }).click();
  await prompt.fill("");
  await prompt.fill("镜头参考 @林澜");
  const menu = page.getByRole("listbox", { name: "引用任务资产" });
  await expect(menu).toBeVisible();
  await menu.getByRole("option", { name: /林澜主视觉/ }).click();
  await expect(prompt).toHaveValue(/<Picture 3>/);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("region", { name: "任务区域" })).toContainText("1 个任务");

  const workspace = await page.request.get(`/api/v1/projects/${project.id}/workspace`);
  const taskId = (await workspace.json()).tasks[0].id as string;
  const editor = await page.request.get(`/api/v1/projects/${project.id}/tasks/${taskId}/editor`);
  expect((await editor.json()).assetBindings).toEqual([
    expect.objectContaining({ assetId: asset.id, reference: "<Picture 3>" }),
  ]);
  await page.locator(".task-list-row:not(.is-create)").dblclick();
  await expect(page.getByRole("button", { name: /图片 3 · ref_image_2 · 林澜主视觉/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /图片 1 · ref_image_0 · 空槽位/ })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("input-slots-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: test.info().outputPath("input-slots-mobile.png") });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole("button", { name: /图片 3 · ref_image_2/ }).click();
  await page.getByRole("button", { name: "清空槽位" }).click();
  await page.getByRole("textbox", { name: "用户提示词", exact: true }).fill("@");
  await expect(page.getByRole("listbox", { name: "引用任务资产" }).getByRole("option")).toHaveCount(0);
  } finally {
    await page.request.patch("/api/v1/application/settings", { data: settings });
  }
});

test("prompt source and visual/text modes stay separate in the simple editor", async ({ page }) => {
  const project = await createProject(page, "提示词模式");
  await openProject(page, project.title);
  await page.getByRole("button", { name: "新建任务" }).click();

  await expect(page.getByRole("textbox", { name: "用户提示词可视化" })).toBeVisible();
  await useTextPrompt(page, "用户版本提示词");
  await page.getByRole("tab", { name: /AI 增强/ }).click();
  await expect(page.getByRole("textbox", { name: "AI 增强提示词可视化" })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await page.getByRole("tab", { name: "用户" }).click();
  await expect(page.getByRole("textbox", { name: "用户提示词" })).toHaveValue("用户版本提示词");
});
