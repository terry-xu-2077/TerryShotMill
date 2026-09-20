import { expect, test } from "@playwright/test";

import { createProject, createTask, openProject, useTextPrompt } from "./helpers";

test("project home creates a project and opens the frozen simple workspace", async ({ page }) => {
  await page.goto("/dev/ui");
  await expect(page.getByRole("main", { name: "项目首页" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Terry导演工作台" })).toBeVisible();

  await page.getByRole("button", { name: /新建项目/ }).click();
  const dialog = page.getByRole("dialog", { name: "新建项目" });
  const title = `UI 主路径 ${Date.now()}`;
  await dialog.getByRole("textbox", { name: "项目名称" }).fill(title);
  await dialog.getByRole("button", { name: /创建项目/ }).click();

  const workspace = page.getByRole("main", { name: "项目工作台" });
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("button", { name: "返回项目首页" })).toBeVisible();
  await expect(workspace.getByRole("button", { name: "项目配置" })).toBeVisible();
  await expect(workspace.getByRole("region", { name: "任务区域" })).toContainText("0 个任务");
  await expect(page.getByRole("navigation", { name: "主导航" })).toHaveCount(0);
});

test("a new task is only created after Save and remains the same in list and card views", async ({ page }) => {
  const project = await createProject(page, "任务保存");
  await openProject(page, project.title);

  await page.getByRole("button", { name: "新建任务" }).click();
  await expect(page.getByTestId("simple-task-editor")).toBeVisible();
  await useTextPrompt(page, "角色进入仓库，镜头缓慢向前推进。");
  await page.getByRole("button", { name: "保存" }).click();

  const taskArea = page.getByRole("region", { name: "任务区域" });
  await expect(taskArea).toContainText("1 个任务");
  await expect(taskArea).toContainText("角色进入仓库");
  await page.getByRole("button", { name: "切换为卡片视图" }).click();
  await expect(taskArea).toContainText("#1 新任务 1");

  await taskArea.getByRole("button", { name: /#1 新任务 1/ }).click();
  const info = page.getByRole("complementary", { name: "任务信息" });
  await expect(info).toContainText("角色进入仓库");
  await expect(info.locator("input, textarea, select")).toHaveCount(0);
});

test("double-click edits the same task through the minimal overlay", async ({ page }) => {
  const project = await createProject(page, "任务编辑");
  await createTask(page, project.id);
  await openProject(page, project.title);

  const row = page.getByRole("button", { name: /#1 雨夜抵达仓库/ });
  await row.dblclick();
  await expect(page.getByTestId("simple-task-editor")).toBeVisible();
  const prompt = await useTextPrompt(page, "角色推开仓库大门，光线从门缝中溢出。");
  await expect(prompt).toHaveValue(/光线从门缝中溢出/);
  await page.getByRole("button", { name: "保存" }).click();

  await expect(page.getByRole("region", { name: "任务区域" })).toContainText("光线从门缝中溢出");
});

test("workspace returns home and keeps the project visible", async ({ page }) => {
  const project = await createProject(page, "返回首页");
  await openProject(page, project.title);
  await page.getByRole("button", { name: "返回项目首页" }).click();
  await expect(page.getByRole("main", { name: "项目首页" })).toBeVisible();
  await expect(page.getByRole("button", { name: `打开项目 ${project.title}` })).toBeVisible();
});

test("current pages do not create page-level horizontal overflow", async ({ page }) => {
  const project = await createProject(page, "布局边界");
  await openProject(page, project.title);
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});
