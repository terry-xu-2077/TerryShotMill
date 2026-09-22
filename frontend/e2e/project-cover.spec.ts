import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("video posters, automatic and custom project covers, and direct autoplay form one flow", async ({ page }) => {
  const project = await createProject(page, "封面验收");
  const first = await createTask(page, project.id, "第一个任务");
  const second = await createTask(page, project.id, "第二个任务");
  const image = await page.request.post(`/api/v1/projects/${project.id}/assets`, {
    multipart: { file: { name: "cover.svg", mimeType: "image/svg+xml", buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#3988be"/></svg>') }, name: "蓝色封面" },
  });
  expect(image.ok()).toBeTruthy();
  const asset = await image.json();
  await page.request.patch(`/api/v1/projects/${project.id}`, { data: { description: "项目简介与生产进度" } });
  for (const task of [first, second]) {
    const submitted = await page.request.post(`/api/v1/projects/${project.id}/tasks/${task.id}/generation`, { data: {} });
    expect(submitted.ok()).toBeTruthy();
    const job = await submitted.json();
    await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  }
  const workspace = await (await page.request.get(`/api/v1/projects/${project.id}/workspace`)).json();
  const poster = workspace.tasks[0].primaryResult.previewUrl;
  expect(poster).toContain("/thumbnails/");
  expect((await page.request.get(poster)).headers()["content-type"]).toContain("image/png");
  const settings = await (await page.request.get(`/api/v1/projects/${project.id}/settings`)).json();
  expect(settings.coverUrl).toBe(poster);
  expect(settings.automaticCoverUrl).toBe(poster);
  await page.goto("/dev/ui");
  const folder = page.getByRole("button", { name: `打开项目 ${project.title}` });
  await expect(folder).toContainText("项目简介与生产进度");
  await expect(folder).toContainText("已生成 2/2");
  await expect(folder.locator(".project-folder-cover")).toHaveCSS("background-size", "cover");
  const box = await folder.boundingBox();
  expect(box!.width / box!.height).toBeCloseTo(1, 1);
  await page.screenshot({ path: "test-results/project-folders-light.png" });
  await page.getByRole("button", { name: "暗色", exact: true }).click();
  await page.screenshot({ path: "test-results/project-folders-dark.png" });
  await folder.click();
  for (const name of ["播放视频 · 第一个任务", "播放视频 · 第二个任务", "播放任务 第二个任务 的生成结果"]) {
    await page.getByRole("button", { name, exact: true }).click();
    const player = page.getByRole("dialog").locator("video.is-active");
    await expect.poll(() => player.evaluate((video: HTMLVideoElement) => !video.paused && video.currentTime > 0)).toBe(true);
    await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    if (name.includes("第一个")) await page.getByRole("button", { name: "切换为卡片视图" }).click();
  }
  await page.getByRole("button", { name: "项目配置", exact: true }).click();
  const config = page.getByRole("dialog", { name: "项目配置", exact: true });
  await config.getByRole("button", { name: "选择图片" }).click();
  await page.getByRole("dialog", { name: "选择封面图片" }).getByRole("button", { name: "设为封面" }).click();
  await config.getByRole("button", { name: "保存", exact: true }).click();
  await expect(config).toHaveCount(0);
  let saved = await (await page.request.get(`/api/v1/projects/${project.id}/settings`)).json();
  expect(saved.coverAssetId).toBe(asset.id);
  await page.getByRole("button", { name: "项目配置", exact: true }).click();
  await config.getByRole("button", { name: "从视频截取" }).click();
  const capture = page.getByRole("dialog", { name: "截取视频封面" });
  await expect(capture.getByRole("button", { name: "使用当前画面" })).toBeEnabled();
  await capture.locator("video").evaluate((video: HTMLVideoElement) => { video.currentTime = 0.5; });
  await expect(capture.getByRole("button", { name: "使用当前画面" })).toBeEnabled();
  await capture.getByRole("button", { name: "使用当前画面" }).click();
  await expect(config.getByRole("img", { name: "项目封面" })).toHaveAttribute("src", /^data:image\/png/);
  // Switching configuration tabs must retain the unsaved captured cover preview.
  await config.getByRole("button", { name: "资产管理" }).click();
  await config.getByRole("button", { name: "放大 蓝色封面" }).click();
  await page.getByRole("button", { name: "关闭大图" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await config.getByRole("button", { name: "项目信息" }).click();
  await expect(config.getByRole("img", { name: "项目封面" })).toHaveAttribute("src", /^data:image\/png/);
  await config.getByRole("button", { name: "保存", exact: true }).click();
  await expect(config).toHaveCount(0);
  saved = await (await page.request.get(`/api/v1/projects/${project.id}/settings`)).json();
  expect(saved.coverAssetId).toMatch(/^cover-/);
  expect(saved.coverUrl).not.toBe(poster);
  await openProject(page, project.title);
  await page.getByRole("button", { name: "项目配置", exact: true }).click();
  await config.getByRole("button", { name: "恢复自动" }).click();
  await expect(config.getByRole("img", { name: "项目封面" })).toHaveAttribute("src", poster);
  await config.getByRole("button", { name: "保存", exact: true }).click();
  await expect(config).toHaveCount(0);
  saved = await (await page.request.get(`/api/v1/projects/${project.id}/settings`)).json();
  expect(saved.coverAssetId).toBeNull();
  expect(saved.coverUrl).toBe(poster);
});
