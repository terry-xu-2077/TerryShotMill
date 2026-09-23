import { expect, test } from "@playwright/test";
import { selectAllTasks, createProject, createTask, openProject } from "./helpers";

test("theme stays in the same corner and local controls keep their scope", async ({ page }) => {
  const project = await createProject(page, "区域布局");
  await createTask(page, project.id, "第一条");
  await createTask(page, project.id, "第二条");
  await page.goto("/");
  const theme = page.locator(".theme-switch");
  const homeTheme = await theme.boundingBox();
  await page.getByRole("button", { name: `打开项目 ${project.title}` }).click();
  expect(await theme.boundingBox()).toEqual(homeTheme);
  await expect(page.locator(".project-workspace-topbar").getByRole("button", { name: "表格" })).toHaveCount(0);
  const area = page.getByRole("region", { name: "任务区域" });
  const cards = area.getByRole("button", { name: "切换为卡片视图", exact: true });
  expect(await cards.textContent()).toBe("");
  await page.locator(".task-list-row:not(.is-create)").nth(1).click();
  await cards.click();
  await expect(page.locator(".task-card-item.is-selected")).toContainText("第二条");
  await expect(page.locator(".workspace-project-title button")).toHaveCount(0);
  await page.locator(".workspace-navigation").getByRole("button", { name: "项目配置" }).click();
  await expect(page.getByRole("dialog", { name: "项目配置" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "项目标题" })).toHaveValue(project.title);
});

test("single generation submits only the current task, and select-all generation includes the project", async ({ page }) => {
  const project = await createProject(page, "生成入口");
  const first = await createTask(page, project.id, "第一条");
  const second = await createTask(page, project.id, "第二条");
  let releaseCheck!: () => void;
  const holdCheck = new Promise<void>(resolve => { releaseCheck = resolve; });
  const checks: string[][] = [];
  const submissions: string[][] = [];
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, async (route) => {
    const { taskIds } = route.request().postDataJSON();
    checks.push(taskIds);
    await holdCheck;
    await route.fulfill({ json: { eligibleTaskIds: taskIds, skipped: [] } });
  });
  await page.route(`**/projects/${project.id}/video-generation-batches`, async (route) => {
    const { taskIds } = route.request().postDataJSON();
    submissions.push(taskIds);
    await route.fulfill({ json: { batchId: "test-batch", eligibleTaskIds: taskIds, skipped: [] } });
  });
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").nth(1).click();
  await page.getByRole("button", { name: "生成视频", exact: true }).click();
  const submitting = page.getByRole("button", { name: "正在提交", exact: true });
  await expect(submitting).toBeDisabled();
  await expect(submitting.locator('.task-stop-spinner')).toBeVisible();
  releaseCheck();
  const single = page.getByRole("dialog", { name: "生成当前视频" });
  await expect.poll(() => submissions.length).toBe(1);
  await expect(single).toHaveCount(0);
  expect(checks[0]).toEqual([second.id]);
  expect(submissions).toEqual([[second.id]]);
  await expect(page.locator(".task-list-row.is-selected")).toContainText("第二条");
  await expect(page.getByRole("complementary", {name:"任务信息"})).toContainText("任务名：第二条");
  await selectAllTasks(page);
  await page.getByRole("button", { name: "生成视频", exact: true }).click();
  const queue = page.getByRole("dialog", { name: "批量生成视频" });
  await queue.getByRole("button", { name: "生成 2 个视频" }).click();
  await expect(queue).toHaveCount(0);
  expect(checks[1]).toEqual([first.id, second.id]);
  expect(submissions[1]).toEqual([first.id, second.id]);
});

test("queue respects multi-selection and excludes tasks with execution errors", async ({ page }) => {
  const project = await createProject(page, "选中生成");
  const first = await createTask(page, project.id, "第一条");
  await createTask(page, project.id, "第二条");
  const third = await createTask(page, project.id, "第三条");
  const checks: string[][] = [];
  const submissions: string[][] = [];
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, async (route) => {
    checks.push(route.request().postDataJSON().taskIds);
    await route.fulfill({ json: { eligibleTaskIds: [third.id], skipped: [{ taskId: first.id, reason: "invalid-params" }] } });
  });
  await page.route(`**/projects/${project.id}/video-generation-batches`, async (route) => {
    const { taskIds } = route.request().postDataJSON();
    submissions.push(taskIds);
    await route.fulfill({ json: { batchId: "test-batch", eligibleTaskIds: taskIds, skipped: [] } });
  });
  await openProject(page, project.title);
  const rows = page.locator(".task-list-row:not(.is-create)");
  await rows.nth(0).click({ modifiers: ["Control"] });
  await rows.nth(2).click({ modifiers: ["Control"] });
  await page.getByRole("button", { name: "切换为卡片视图", exact: true }).click();
  await expect(page.locator(".task-card-item.is-batch-selected")).toHaveCount(2);
  await page.screenshot({ path: "test-results/task-multiselect-cards.png", animations: "disabled" });
  await page.getByRole("button", { name: "生成视频", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "批量生成视频" });
  await expect(dialog).toContainText("1 个参数无效，不会提交");
  await dialog.getByRole("button", { name: "生成 1 个视频" }).click();
  await expect(dialog).toHaveCount(0);
  expect(checks).toEqual([[first.id, third.id]]);
  expect(submissions).toEqual([[third.id]]);
});

test("unreviewed tasks can be generated and request failures are visible", async ({ page }) => {
  const project = await createProject(page, "生成检查");
  const task = await createTask(page, project.id);
  let submitted = false;
  await page.route(`**/projects/${project.id}/video-generation-batches`, async route => {
    submitted = true;
    await route.fulfill({json:{batchId:"direct",eligibleTaskIds:[task.id],skipped:[]}});
  });
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").first().click();
  await page.getByRole("button", { name: "生成视频", exact: true }).click();
  await expect.poll(() => submitted).toBe(true);
  await expect(page.getByRole("dialog", {name:"生成当前视频"})).toHaveCount(0);
  await expect(page.locator(".task-list-row.is-selected")).toHaveCount(1);
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, (route) => route.fulfill({ status: 503, json: {} }));
  await page.getByRole("button", { name: "生成视频", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("无法检查生成条件");
  await expect(page.getByRole("button", { name: "生成 0 个视频" })).toBeDisabled();
});

test("empty project has no selection actions", async ({ page }) => {
  const project = await createProject(page, "空项目生成");
  await openProject(page, project.title);
  await expect(page.getByRole("region", { name: "任务操作" })).toHaveCount(0);
});

test("visible checkboxes support keyboard selection, both views, select all and clear", async ({ page }) => {
  const project = await createProject(page, "可见多选");
  await createTask(page, project.id, "第一条");
  await createTask(page, project.id, "第二条");
  await openProject(page, project.title);
  await expect(page.locator(".task-list-row:not(.is-create) .task-preview").first()).toHaveCSS("background-size", "cover");
  await page.getByRole("button", { name: "管理任务", exact: true }).click();
  const first = page.getByRole("checkbox", { name: "选择任务 · 第一条", exact: true });
  await first.focus();
  await first.press("Space");
  await expect(first).toBeChecked();
  await expect(page.locator(".task-action-dock").getByRole("region", { name: "任务操作" })).toBeVisible();
  await page.getByRole("button", { name: "切换为卡片视图", exact: true }).click();
  await expect(first).toBeChecked();
  const mediaSelection = page.locator(".is-card .tc-checkbox-media").first();
  await expect(mediaSelection).toBeVisible();
  await expect(page.locator(".task-card-preview-wrap > .task-preview").first()).toHaveCSS("background-size", "cover");
  await expect(mediaSelection.locator(".tc-check-box")).toHaveCSS("width", "24px");
  await expect(mediaSelection.locator(".tc-check-box")).toHaveCSS("height", "24px");
  await expect(mediaSelection.locator(".tc-check-box")).toHaveCSS("border-radius", "6px");
  await expect(mediaSelection.locator("svg")).toHaveCount(1);
  await expect(page.locator(".is-card > .task-selection-control").first()).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    const fill = await mediaSelection.locator(".tc-check-box").evaluate(el => getComputedStyle(el).backgroundColor);
    expect(fill).toMatch(/0\.72/);
  }
  await page.screenshot({ path: "test-results/task-media-selection.png" });
  await page.locator(".task-selection-control").filter({ has: page.getByRole("checkbox", { name: "选择任务 · 第二条", exact: true }) }).click();
  await expect(page.getByRole("checkbox", { name: "选择任务 · 第二条", exact: true })).toBeChecked();
  await expect(page.locator(".task-card-item.is-batch-selected")).toHaveCount(2);
  await page.getByRole("button", { name: "取消选择", exact: true }).click();
  await expect(first).not.toBeChecked();
  await selectAllTasks(page);
  await expect(page.locator(".task-card-item.is-batch-selected")).toHaveCount(2);
  await page.getByRole("button", { name: "取消选择", exact: true }).click();
  await expect(page.locator(".task-card-item.is-batch-selected")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await selectAllTasks(page);
  await expect(page.getByRole("button", { name: "增强提示词", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const navigation = await page.locator(".workspace-navigation").boundingBox();
  const theme = await page.locator(".theme-switch").boundingBox();
  const title = await page.locator(".workspace-project-title").boundingBox();
  const bridge = await page.locator(".bridge-connection").boundingBox();
  expect(navigation!.x + navigation!.width).toBeLessThanOrEqual(theme!.x);
  expect(title!.x + title!.width).toBeLessThanOrEqual(bridge!.x);
  await page.screenshot({ path: "test-results/task-controls-narrow.png", animations: "disabled" });
});

test("batch enhancement defaults to all tasks and respects explicit selection", async ({ page }) => {
  const project = await createProject(page, "增强入口");
  const first = await createTask(page, project.id, "第一条");
  const second = await createTask(page, project.id, "第二条");
  const third = await createTask(page, project.id, "第三条");
  const requests: string[][] = [];
  await page.route(`**/projects/${project.id}/prompt-enhancement-batches`, async (route) => {
    requests.push(route.request().postDataJSON().taskIds);
    await route.fulfill({ json: { batchId: "test-enhancement", state: "queued", items: [] } });
  });
  await openProject(page, project.title);
  await selectAllTasks(page);
  const open = page.getByRole("button", { name: "增强提示词", exact: true });
  const dialog = page.getByRole("dialog", { name: "批量 AI 增强", exact: true });
  await open.click();
  await expect(dialog).toContainText("已选择 3 个任务");
  await expect(dialog).toContainText("3 个任务可增强");
  await dialog.getByRole("button", { name: "开始增强", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(requests).toEqual([[first.id, second.id, third.id]]);
  await page.getByRole("button", { name: "取消选择", exact: true }).click();
  await page.locator(".task-selection-control").filter({ has: page.getByRole("checkbox", { name: "选择任务 · 第二条", exact: true }) }).click();
  await expect(page.getByRole("checkbox", { name: "选择任务 · 第二条", exact: true })).toBeChecked();
  await page.locator(".task-selection-control").filter({ has: page.getByRole("checkbox", { name: "选择任务 · 第三条", exact: true }) }).click();
  await open.click();
  await expect(dialog).toContainText("已选择 2 个任务");
  await expect(dialog).toContainText("2 个任务可增强");
  await dialog.getByRole("button", { name: "开始增强", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(requests[1]).toEqual([second.id, third.id]);
});

test("submission failure keeps the confirmation open with an error instead of claiming success", async ({ page }) => {
  const project = await createProject(page, "提交失败");
  const task = await createTask(page, project.id);
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, (route) => route.fulfill({ json: { eligibleTaskIds: [task.id], skipped: [] } }));
  await page.route(`**/projects/${project.id}/video-generation-batches`, (route) => route.fulfill({ status: 503, json: {} }));
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").first().click();
  await page.getByRole("button", { name: "生成视频", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "生成当前视频" });
  await expect(dialog.getByRole("alert")).toContainText("生成提交未确认");
  await expect(dialog.getByRole("button", { name: "取消" })).toBeEnabled();
});
