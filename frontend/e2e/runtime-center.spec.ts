import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("runtime center keeps failed history after refresh and retries only the failed task", async ({ page }) => {
  const project = await createProject(page, "运行恢复");
  const success = await createTask(page, project.id, "正常任务");
  const failure = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: {
      title: "需要重试的任务", userPrompt: `E2E_FAIL_ONCE ${project.id}`,
      userIntent: "雨夜码头", promptSource: "user", durationSeconds: 6,
      generation: { resolution: "1080p", quality: "标准", mode: "全能参考", contextMode: "不承接" },
      assetBindings: [],
    },
  });
  expect(failure.ok()).toBeTruthy();
  const failedTask = await failure.json();
  const submitted = await page.request.post(`/api/v1/projects/${project.id}/prompt-enhancement-batches`, {
    data: { taskIds: [success.id, failedTask.id] },
  });
  expect(submitted.ok()).toBeTruthy();
  const batchId = (await submitted.json()).batchId;
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/projects/${project.id}/prompt-enhancement-batches/${batchId}`);
    return (await response.json()).state;
  }).toBe("partial");
  await openProject(page, project.title);
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${project.title}` }).click();
  const elapsed = page.locator(".task-list-row .task-elapsed");
  await expect(elapsed).toHaveCount(2);
  await expect(elapsed.nth(0)).toContainText("增强");
  await expect(elapsed.nth(1)).toContainText("增强");
  await page.locator(".task-list-row:not(.is-create)").nth(1).click();
  await expect(page.getByRole("complementary", { name: "任务信息" })).toContainText("增强排队耗时");
  await page.getByRole("button", { name: "切换为卡片视图", exact: true }).click();
  await expect(page.locator(".task-card-item .task-elapsed")).toHaveCount(2);
  await page.getByRole("button", { name: "运行中心", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "运行中心", exact: true });
  const projectHistory = dialog.locator('.runtime-project').filter({ has: page.locator('.runtime-project-summary', { hasText: project.title }) });
  await expect(projectHistory.locator('.runtime-task').filter({ hasText: '正常任务' })).toContainText('已完成');
  await expect(projectHistory.locator('.runtime-task').filter({ hasText: '需要重试的任务' })).toContainText('失败');
  await expect(dialog).toContainText("增强服务不可用，请检查连接后重试。");
  const retryRequest = page.waitForResponse((response) => response.url().endsWith(`/prompt-enhancement-batches/${batchId}/retry-failed`));
  await projectHistory.getByRole("button", { name: "重试失败项" }).click();
  const retry = await (await retryRequest).json();
  expect(retry.items.map((item: { taskId: string }) => item.taskId)).toEqual([failedTask.id]);
  await expect(projectHistory.locator('.runtime-task.is-completed').filter({ hasText: '需要重试的任务' })).toHaveCount(1);
  await expect(projectHistory.locator('.runtime-task.is-failed').filter({ hasText: '需要重试的任务' })).toHaveCount(1);
  await page.screenshot({ path: "test-results/runtime-center-desktop.png" });
});

test("cancels waiting videos, keeps the running result and retains cancellation after reload", async ({ page }) => {
  const project = await createProject(page, "取消待执行视频");
  const runningResponse = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: { title: "正在生成", userPrompt: "E2E_HOLD_VIDEO 荒星", promptSource: "user" },
  });
  expect(runningResponse.ok()).toBeTruthy();
  const runningTask = await runningResponse.json();
  const runningResponse2 = await page.request.post(`/api/v1/projects/${project.id}/tasks/${runningTask.id}/generation`, { data: {} });
  expect(runningResponse2.ok()).toBeTruthy();
  const runningJob = await runningResponse2.json();
  try {
    await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${runningJob.id}`)).json()).status).toBe("running");
    const queuedTask = await createTask(page, project.id, "等待生成");
    const queuedResponse = await page.request.post(`/api/v1/projects/${project.id}/tasks/${queuedTask.id}/generation`, { data: {} });
    expect(queuedResponse.ok()).toBeTruthy();
    const queuedJob = await queuedResponse.json();
    await openProject(page, project.title);
    await page.getByRole("button", { name: "运行中心", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "运行中心", exact: true });
    const cancellation = page.waitForResponse(response => response.url().endsWith("/video-generation-queue/cancel"));
    await dialog.getByRole("button", { name: "取消待执行视频" }).click();
    const response = await cancellation;
    expect(response.ok()).toBeTruthy();
    expect(await response.json()).toEqual({ cancelledJobIds: [queuedJob.id] });
    await expect(dialog.getByText("已取消", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "取消待执行视频" })).toHaveCount(0);
    const running = await (await page.request.get(`/api/v1/jobs/${runningJob.id}`)).json();
    expect(running.status).toBe("running");
    await page.reload();
    await page.getByRole("button", { name: `打开项目 ${project.title}` }).click();
    await page.getByRole("button", { name: "运行中心", exact: true }).click();
    await expect(dialog.getByText("已取消", { exact: true })).toBeVisible();
    const workspace = await (await page.request.get(`/api/v1/projects/${project.id}/workspace`)).json();
    expect(workspace.tasks.find((task: { id: string }) => task.id === queuedTask.id).resultCount).toBe(0);
  } finally {
    await page.request.post(`/api/v1/__e2e/videos/${runningJob.id}/release`);
  }
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${runningJob.id}`)).json()).status).toBe("completed");
});
