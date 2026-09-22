import { expect, test } from "@playwright/test";
import { selectAllTasks, createProject, createTask, openProject } from "./helpers";

test("prompt batch previews empty tasks and only submits eligible tasks", async ({ page }) => {
  await page.setViewportSize({ width: 960, height: 540 });
  const project = await createProject(page, "增强预览");
  const ready = await createTask(page, project.id, "可执行任务");
  const root = `/api/v1/projects/${project.id}`;
  const empty = await (await page.request.post(`${root}/tasks`, { data: { title: "空任务" } })).json();
  let submitted: string[] = [];
  page.on("request", request => {
    if (request.url().endsWith("/prompt-enhancement-batches") && request.method() === "POST") submitted = request.postDataJSON().taskIds;
  });
  await openProject(page, project.title);
  await selectAllTasks(page);
  await page.getByRole("button", { name: "增强提示词", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "批量 AI 增强" });
  await expect(dialog).toContainText("已选择 2 个任务");
  await expect(dialog).toContainText("1 个任务可增强");
  await expect(dialog).toContainText("1 个任务缺少用户提示词，不会提交");
  expect(submitted).toEqual([]);
  await dialog.screenshot({ path: "test-results/prompt-batch-preview.png" });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "暗色", exact: true }).click();
  await page.getByRole("button", { name: "增强提示词", exact: true }).click();
  await expect(dialog).toContainText("1 个任务可增强");
  const bounds = await dialog.boundingBox();
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(540);
  await dialog.screenshot({ path: "test-results/prompt-batch-preview-dark.png" });
  await dialog.getByRole("button", { name: "开始增强", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(submitted).toEqual([ready.id]);
  await expect.poll(async () => (await (await page.request.get(`${root}/tasks/${ready.id}/prompt-revisions`)).json()).items?.length).toBe(1);
  const workspace = await (await page.request.get(`${root}/workspace`)).json();
  expect(workspace.runtime.promptBatches[0].items.map((item: { taskId: string }) => item.taskId)).toEqual([ready.id]);
  expect((await (await page.request.get(`${root}/tasks/${empty.id}/editor`)).json()).userPrompt).toBe("");
});

test("changed task eligibility requires confirmation again and supports rechecking", async ({ page }) => {
  const project = await createProject(page, "增强状态变化");
  const first = await createTask(page, project.id, "任务一");
  const second = await createTask(page, project.id, "任务二");
  const root = `/api/v1/projects/${project.id}`;
  let checks = 0;
  let submissions = 0;
  await page.route(`**${root}/prompt-enhancement-batches/eligibility`, async route => {
    checks += 1;
    await route.fulfill({ json: checks === 1 ? { eligibleTaskIds: [first.id, second.id], skipped: [] } : {
      eligibleTaskIds: [], skipped: [first, second].map(task => ({ taskId: task.id, reason: "busy", message: "正在增强或排队" })),
    } });
  });
  page.on("request", request => { if (request.url().endsWith("/prompt-enhancement-batches") && request.method() === "POST") submissions += 1; });
  await openProject(page, project.title);
  await selectAllTasks(page);
  await page.getByRole("button", { name: "增强提示词", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "批量 AI 增强" });
  await expect(dialog).toContainText("2 个任务可增强");
  await dialog.getByRole("button", { name: "开始增强", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("任务状态已变化");
  await expect(dialog).toContainText("2 个任务正在增强或排队，不会提交");
  await expect(dialog.getByRole("button", { name: "开始增强", exact: true })).toBeDisabled();
  expect(submissions).toBe(0);
  await page.unroute(`**${root}/prompt-enhancement-batches/eligibility`);
  await dialog.getByRole("button", { name: "重新检查", exact: true }).click();
  await expect(dialog).toContainText("2 个任务可增强");
  await expect(dialog.getByRole("button", { name: "开始增强", exact: true })).toBeEnabled();
});

test("failed prompt preview blocks submission and retry keeps context choices", async ({ page }) => {
  const project = await createProject(page, "增强预览重试");
  await createTask(page, project.id);
  await createTask(page, project.id, "第二任务");
  await page.route("**/prompt-enhancement-batches/eligibility", route => route.fulfill({ status: 503, json: {} }), { times: 1 });
  await openProject(page, project.title);
  await selectAllTasks(page);
  await page.getByRole("button", { name: "增强提示词", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "批量 AI 增强" });
  await expect(dialog.getByRole("alert")).toContainText("任务状态检查失败");
  await expect(dialog.getByRole("button", { name: "开始增强", exact: true })).toBeDisabled();
  await dialog.getByRole("checkbox", { name: "上一任务摘要", exact: true }).focus();
  await page.keyboard.press("Space");
  await dialog.getByRole("button", { name: "重试检查", exact: true }).click();
  await expect(dialog).toContainText("2 个任务可增强");
  await expect(dialog.getByRole("checkbox", { name: "上一任务摘要", exact: true })).toBeChecked();
  await expect(dialog.getByRole("button", { name: "开始增强", exact: true })).toBeEnabled();
});
