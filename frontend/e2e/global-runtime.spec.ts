import { expect, test } from "@playwright/test";
import { createProject, openProject } from "./helpers";

test("global footer stays at the bottom and runtime folds by project and kind with flat task rows", async ({ page }, info) => {
  const a = await createProject(page, "全局运行甲");
  const b = await createProject(page, "全局运行乙");
  let cancelled = false;
  await page.route("**/api/v1/projects/runtime", route => route.fulfill({ json: [
    { project: { id: a.id, title: a.title }, runtime: { state: "idle", promptBatches: [], videoJobs: [] } },
    { project: { id: b.id, title: b.title }, runtime: { state: "queued", promptBatches: [], videoJobs: [{ id: "b-job", taskId: "b-task", title: "另一项目的视频", state: cancelled ? "cancelled" : "queued" }] } },
  ] }));
  await page.route(`**/api/v1/projects/${b.id}/video-generation-queue/cancel`, async route => {
    expect(route.request().postDataJSON()).toEqual({ jobIds: ["b-job"] });
    cancelled = true;
    await route.fulfill({ json: { cancelledJobIds: ["b-job"] } });
  });
  await page.goto("/dev/ui");
  const bar = page.getByRole("contentinfo", { name: "全局状态栏" });
  await expect(bar).toBeVisible();
  await expect(bar).toContainText("排队 1 项");
  const box = await bar.boundingBox();
  expect(Math.abs(box!.y + box!.height - page.viewportSize()!.height)).toBeLessThan(2);
  await bar.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "设置", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await openProject(page, a.title);
  await expect(bar).toContainText("排队 1 项");
  await bar.getByRole("button", { name: "运行中心", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "运行中心" });
  const project = dialog.locator(".runtime-project").filter({ has: page.locator(".runtime-project-summary", { hasText: b.title }) });
  await expect(project.getByText("另一项目的视频", { exact: true })).toBeVisible();
  await project.locator(".runtime-project-summary").click();
  await expect(project.getByText("另一项目的视频", { exact: true })).not.toBeVisible();
  await page.waitForTimeout(5200);
  await expect(project).not.toHaveAttribute("open", "");
  await project.locator(".runtime-project-summary").click();
  const category = project.locator(".runtime-category").filter({ has: page.locator("summary", { hasText: "视频生成" }) });
  await category.locator(":scope > summary").click();
  await expect(project.getByText("另一项目的视频", { exact: true })).not.toBeVisible();
  await category.locator(":scope > summary").click();
  await expect(project.locator(".runtime-task details, details.runtime-task")).toHaveCount(0);
  await expect(project.locator(".runtime-task-line")).toContainText("排队中");
  await project.getByRole("button", { name: "取消待执行视频" }).click();
  await expect(project.getByRole("button", { name: "取消待执行视频" })).toHaveCount(0);
  await expect(project.locator(".runtime-task-line")).toContainText("已取消");
  await page.screenshot({ path: info.outputPath("global-runtime.png") });
});

test("runtime task controls sort, suspend, resume and remove without touching running jobs", async ({ page }) => {
  let jobs = [
    { id: "one", taskId: "t1", title: "任务甲", state: "queued", position: 0, paused: false },
    { id: "two", taskId: "t2", title: "任务乙", state: "queued", position: 1, paused: false },
    { id: "running", taskId: "t3", title: "运行任务", state: "running", position: 2, paused: false },
  ];
  await page.route("**/api/v1/projects/runtime", route => route.fulfill({ json: [{ project: { id: "p", title: "控制测试" }, runtime: { state: "running", promptBatches: [], videoJobs: jobs } }] }));
  await page.route("**/api/v1/projects/p/runtime/video/*", async route => {
    const id = route.request().url().split("/").at(-1);
    const action = route.request().postDataJSON().action;
    const job = jobs.find(item => item.id === id)!;
    if (action === "pause" || action === "resume") job.paused = action === "pause";
    if (action === "up") { job.position = 0; jobs.find(item => item.id === "one")!.position = 1; }
    if (action === "remove") jobs = jobs.filter(item => item.id !== id);
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "运行中心", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "运行中心" });
  await dialog.getByRole("button", { name: "上移 任务乙", exact: true }).click();
  await expect(dialog.locator(".runtime-task-title").first()).toHaveText("任务乙");
  await dialog.getByRole("button", { name: "挂起 任务乙", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "恢复 任务乙", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "恢复 任务乙", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "挂起 任务乙", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "移除 任务甲", exact: true }).click();
  await expect(dialog.getByText("任务甲", { exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /(?:移除|挂起|上移|下移) 运行任务/ })).toHaveCount(0);
});
