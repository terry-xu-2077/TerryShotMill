import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("queued and generating tasks remain distinct in both views and details", async ({ page }) => {
  const project = await createProject(page, "视频队列状态");
  await createTask(page, project.id, "等待项");
  await createTask(page, project.id, "正在生成项");
  await page.route(`**/projects/${project.id}/workspace`, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.tasks.forEach((task: { title: string; status: string; videoGenerationStatus: string }) => {
      task.status = "running";
      task.videoGenerationStatus = task.title === "等待项" ? "queued" : "running";
    });
    await route.fulfill({ json: data });
  });
  await page.route('**/api/v1/projects/runtime', route => route.fulfill({ json: [{ project,
    runtime: { state: 'running', videoJobs: [
      { id: 'queued', taskId: 'queued', title: '等待项', state: 'queued' },
      { id: 'running', taskId: 'running', title: '正在生成项', state: 'running' },
    ] },
  }] }));
  await openProject(page, project.title);
  const area = page.getByRole("region", { name: "任务区域" });
  for (const view of ["卡片", "表格"]) {
    await expect(area.getByRole("button").filter({ hasText: "#1 等待项" })).toContainText("排队中");
    await expect(area.getByRole("button").filter({ hasText: "#2 正在生成项" })).toContainText("生成中");
    await expect(page.locator(".workspace-runtime-summary")).toContainText("执行中 1 项");
    await expect(page.locator(".workspace-runtime-summary")).toContainText("排队 1 项");
    await area.getByText("#1 等待项", { exact: true }).click();
    await expect(page.getByRole("complementary", { name: "任务信息" })).toContainText("排队中");
    await page.getByRole("button", { name: `切换为${view}视图` }).click();
  }
});

test("active video tasks open read-only and become editable after completion", async ({ page }, testInfo) => {
  const project = await createProject(page, "生成任务只读");
  const task = await createTask(page, project.id, "只读镜头");
  let status = "queued";
  let contentWrites = 0;
  page.on("request", request => {
    if (request.url().endsWith(`/tasks/${task.id}`) && ["PATCH", "PUT"].includes(request.method())) contentWrites++;
  });
  await page.route(`**/projects/${project.id}/workspace`, async route => {
    const response = await route.fetch();
    const data = await response.json();
    const current = data.tasks.find((item: { id: string }) => item.id === task.id);
    current.status = status;
    current.videoGenerationStatus = status;
    await route.fulfill({ json: data });
  });
  await page.route('**/api/v1/projects/runtime', route => route.fulfill({ json: [{ project,
    runtime: { state: status, videoJobs: [{ id: 'readonly', taskId: task.id, title: '只读镜头', state: status }] },
  }] }));
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").dblclick();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("排队或生成中 · 只读")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "保存", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("textbox", { name: "用户提示词可视化" })).toHaveAttribute("contenteditable", "false");
  await dialog.getByRole("button", { name: "生成参数", exact: true }).click();
  await expect(dialog.getByRole("slider", { name: "总秒数" })).toBeDisabled();
  await expect(dialog.getByRole("combobox", { name: "生成工作流" })).toBeDisabled();
  await dialog.getByRole("tablist", { name: "用户提示词显示模式" }).getByRole("tab", { name: /文本/ }).click();
  const prompt = dialog.getByRole("textbox", { name: "用户提示词", exact: true });
  await expect(prompt).toHaveAttribute("readonly", "");
  const original = await prompt.inputValue();
  await prompt.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("不能写入");
  await expect(prompt).toHaveValue(original);
  await dialog.getByRole("tab", { name: "AI 增强", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "增强", exact: true })).toHaveCount(0);
  expect(contentWrites).toBe(0);

  // An isolated fake generation emits real project events to refresh the open window.
  status = "running";
  const notifier = await createTask(page, project.id, "触发运行状态同步");
  expect((await page.request.post(`/api/v1/projects/${project.id}/tasks/${notifier.id}/generation`, { data: {} })).ok()).toBeTruthy();
  await expect(page.locator(".workspace-runtime-summary")).toContainText("执行中 1 项");
  await expect(dialog.getByText("排队或生成中 · 只读")).toBeVisible();
  await dialog.getByRole("tab", { name: "用户", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("running-readonly.png") });

  status = "completed";
  const completedNotifier = await createTask(page, project.id, "触发完成状态同步");
  expect((await page.request.post(`/api/v1/projects/${project.id}/tasks/${completedNotifier.id}/generation`, { data: {} })).ok()).toBeTruthy();
  await expect(dialog.getByRole("button", { name: "保存", exact: true })).toBeVisible();
  await expect(dialog.getByText("排队或生成中 · 只读")).toHaveCount(0);
  await expect(dialog.getByRole("textbox", { name: "用户提示词", exact: true })).not.toHaveAttribute("readonly");
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toBeVisible();
  expect(contentWrites).toBe(0);
});


test("dependent video displays waiting without a missing-context sticker", async ({ page }) => {
  const project = await createProject(page, "批量承接等待");
  await createTask(page, project.id, "等待尾帧");
  await page.route(`**/projects/${project.id}/workspace`, async route => {
    const response = await route.fetch();
    const data = await response.json();
    Object.assign(data.tasks[0], { status: "running", videoGenerationStatus: "queued",
      generationStatusNote: "等待上一任务结果", generationWarnings: [] });
    await route.fulfill({ json: data });
  });
  await openProject(page, project.title);
  const row = page.locator('.task-list-row:not(.is-create)');
  await expect(row).toContainText('等待上一任务结果');
  await expect(page.getByRole('button', { name: '查看任务生成风险' })).toHaveCount(0);
  await row.click();
  await expect(page.getByRole('complementary', { name: '任务信息' })).toContainText('等待上一任务结果');
  await page.getByRole('button', { name: '切换为卡片视图' }).click();
  await expect(page.locator('.task-card-item:not(.is-create)')).toContainText('等待上一任务结果');
});
