import { expect, test } from "@playwright/test";

import { selectAllTasks, createProject, createTask, openProject } from "./helpers";

test("mobile viewport can open the current project workspace without page overflow", async ({ page }) => {
  const project = await createProject(page, "手机布局");
  await openProject(page, project.title);
  await expect(page.getByRole("button", { name: "返回项目首页" })).toBeVisible();
  await expect(page.getByRole("button", { name: "项目配置" })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});

test("mobile workspace top controls receive taps after task selection", async ({ page }) => {
  const project = await createProject(page, "手机顶部点击");
  await createTask(page, project.id);
  await openProject(page, project.title);
  // Do not select a task first: selection moves the initially hidden action dock.
  await page.getByRole("button", { name: "项目配置", exact: true }).tap({ timeout: 5000 });
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await selectAllTasks(page);
  await page.getByRole("button", { name: "切换为卡片视图" }).tap();
  await expect(page.getByRole("button", { name: "切换为表格视图" })).toBeVisible();
  await page.getByRole("button", { name: "项目配置", exact: true }).tap();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByRole("button", { name: "亮色", exact: true }).tap();
  await expect(page.locator("html")).toHaveAttribute("data-tc-mode", "light");
  await page.getByRole("button", { name: "返回项目首页" }).tap();
  await expect(page.getByRole("main", { name: "项目首页" })).toBeVisible();
});

test("mobile controls remain tappable with a long selection scrolled out of view", async ({ page }) => {
  const project = await createProject(page, "手机长列表点击");
  for (let i = 0; i < 12; i++) await createTask(page, project.id, `任务 ${i + 1}`);
  await openProject(page, project.title);
  await selectAllTasks(page);
  await page.locator(".task-list-view").evaluate(el => { el.scrollTop = 300; });
  await page.getByRole("button", { name: "项目配置", exact: true }).tap();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.locator(".task-list-view").evaluate(el => { el.scrollTop = 0; });
  await page.getByRole("button", { name: "取消选择", exact: true }).tap();
  await expect(page.getByRole("button", { name: "完成管理", exact: true })).toBeVisible();
});

test("single and management actions stay above the status bar", async ({ page }) => {
  const project = await createProject(page, "底栏避让");
  await createTask(page, project.id);
  await openProject(page, project.title);
  await page.locator('.task-list-row:not(.is-create)').first().tap();
  for (const management of [false, true]) {
    if (management) await selectAllTasks(page);
    const bar = page.getByRole('region', { name: '任务操作', exact: true });
    await expect(bar).toBeVisible();
    await expect.poll(async () => {
      const actions = (await bar.boundingBox())!;
      const status = (await page.locator('.project-workspace-statusbar').boundingBox())!;
      return status.y - (actions.y + actions.height);
    }).toBeGreaterThanOrEqual(8);
  }
});
