import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

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

test("single generation submits only the current task, and queue generation defaults to the project", async ({ page }) => {
  const project = await createProject(page, "生成入口");
  const first = await createTask(page, project.id, "第一条");
  const second = await createTask(page, project.id, "第二条");
  const checks: string[][] = [];
  const submissions: string[][] = [];
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, async (route) => {
    const { taskIds } = route.request().postDataJSON();
    checks.push(taskIds);
    await route.fulfill({ json: { eligibleTaskIds: taskIds, skipped: [] } });
  });
  await page.route(`**/projects/${project.id}/video-generation-batches`, async (route) => {
    const { taskIds } = route.request().postDataJSON();
    submissions.push(taskIds);
    await route.fulfill({ json: { batchId: "test-batch", eligibleTaskIds: taskIds, skipped: [] } });
  });
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").nth(1).click();
  await page.getByRole("button", { name: "生成当前任务", exact: true }).click();
  const single = page.getByRole("dialog", { name: "生成当前任务" });
  await single.getByRole("button", { name: "生成 1 个视频" }).click();
  await expect(single).toHaveCount(0);
  expect(checks[0]).toEqual([second.id]);
  expect(submissions).toEqual([[second.id]]);
  await page.getByRole("button", { name: "队列生成", exact: true }).click();
  const queue = page.getByRole("dialog", { name: "队列生成" });
  await queue.getByRole("button", { name: "生成 2 个视频" }).click();
  await expect(queue).toHaveCount(0);
  expect(checks[1]).toEqual([first.id, second.id]);
  expect(submissions[1]).toEqual([first.id, second.id]);
});

test("queue respects multi-selection and excludes tasks the server did not approve", async ({ page }) => {
  const project = await createProject(page, "选中生成");
  const first = await createTask(page, project.id, "第一条");
  await createTask(page, project.id, "第二条");
  const third = await createTask(page, project.id, "第三条");
  const checks: string[][] = [];
  const submissions: string[][] = [];
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, async (route) => {
    checks.push(route.request().postDataJSON().taskIds);
    await route.fulfill({ json: { eligibleTaskIds: [third.id], skipped: [{ taskId: first.id, reason: "not-reviewed" }] } });
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
  await page.getByRole("button", { name: "队列生成", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "队列生成" });
  await expect(dialog).toContainText("1 个待检查，不会提交");
  await dialog.getByRole("button", { name: "生成 1 个视频" }).click();
  await expect(dialog).toHaveCount(0);
  expect(checks).toEqual([[first.id, third.id]]);
  expect(submissions).toEqual([[third.id]]);
});

test("unreviewed tasks cannot be generated and request failures are visible", async ({ page }) => {
  const project = await createProject(page, "生成检查");
  await createTask(page, project.id);
  await openProject(page, project.title);
  await page.getByRole("button", { name: "生成当前任务", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "生成当前任务" });
  await expect(dialog).toContainText("待检查，不会提交");
  await expect(dialog.getByRole("button", { name: "生成 0 个视频" })).toBeDisabled();
  await dialog.getByRole("button", { name: "取消" }).click();
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, (route) => route.fulfill({ status: 503, json: {} }));
  await page.getByRole("button", { name: "队列生成", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("无法检查生成条件");
  await expect(page.getByRole("button", { name: "生成 0 个视频" })).toBeDisabled();
});

test("empty project disables both generation commands", async ({ page }) => {
  const project = await createProject(page, "空项目生成");
  await openProject(page, project.title);
  await expect(page.getByRole("button", { name: "生成当前任务", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "队列生成", exact: true })).toBeDisabled();
});

test("submission failure keeps the confirmation open with an error instead of claiming success", async ({ page }) => {
  const project = await createProject(page, "提交失败");
  const task = await createTask(page, project.id);
  await page.route(`**/projects/${project.id}/video-generation-batches/eligibility`, (route) => route.fulfill({ json: { eligibleTaskIds: [task.id], skipped: [] } }));
  await page.route(`**/projects/${project.id}/video-generation-batches`, (route) => route.fulfill({ status: 503, json: {} }));
  await openProject(page, project.title);
  await page.getByRole("button", { name: "生成当前任务", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "生成当前任务" });
  await dialog.getByRole("button", { name: "生成 1 个视频" }).click();
  await expect(dialog.getByRole("alert")).toContainText("生成提交未确认");
  await expect(dialog.getByRole("button", { name: "取消" })).toBeEnabled();
});
