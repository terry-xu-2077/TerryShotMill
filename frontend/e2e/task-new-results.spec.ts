import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("new result stickers replace the quiet title-aligned status", async ({ page }, info) => {
  const project = await createProject(page, "新结果贴纸");
  await createTask(page, project.id, "普通任务");
  await createTask(page, project.id, "新视频任务");
  await createTask(page, project.id, "新增强任务");
  await page.route(`**/api/v1/projects/${project.id}/workspace`, async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.tasks[1].latestVideoResultId = "new-video";
    body.tasks[1].latestPromptRevisionId = "video-prompt";
    body.tasks[2].latestPromptRevisionId = "new-prompt";
    await route.fulfill({ response, json: body });
  });
  await openProject(page, project.title);
  const rows = page.locator(".task-list-row:not(.is-create)");
  await expect(rows.first().locator(".task-plain-status")).toHaveText("未开始");
  await expect(page.getByRole("img", { name: "新视频结果", exact: true })).toHaveText("新");
  await expect(rows.nth(2).getByRole("img", { name: "新提示词增强结果", exact: true })).toHaveText("新");
  await expect(rows.nth(1).locator(".task-plain-status")).toHaveCount(0);
  await page.getByRole("region", { name: "任务区域" }).evaluate(async element => {
    await Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished));
  });
  const video = rows.nth(1).getByRole('img', { name: '新视频结果', exact: true });
  const prompt = rows.nth(1).getByRole('img', { name: '新提示词增强结果', exact: true });
  const videoBox = (await video.boundingBox())!;
  const promptBox = (await prompt.boundingBox())!;
  expect(videoBox.x + videoBox.width).toBeGreaterThan(promptBox.x);
  await expect(video).toHaveCSS('z-index', '1');
  await expect(video.locator('.task-new-sticker-word')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  const title = (await rows.first().locator("strong").boundingBox())!;
  const status = (await rows.first().locator(".task-plain-status").boundingBox())!;
  expect(Math.abs(title.y + title.height / 2 - status.y - status.height / 2)).toBeLessThan(1);
  await rows.nth(1).click();
  const previewNotices = page.locator('.task-info-notices');
  await expect(previewNotices.getByRole('img', { name: '新视频结果', exact: true })).toBeVisible();
  await expect(previewNotices.getByRole('img', { name: '新提示词增强结果', exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("new-stickers.png") });
  await page.getByRole("button", { name: "切换为卡片视图" }).click();
  await expect(page.locator(".task-card-item").getByRole("img", { name: "新视频结果", exact: true })).toBeVisible();
  await expect(page.locator(".task-card-heading .task-plain-status")).toHaveCount(1);
  const card = (await page.locator('.task-collection-item.is-card').first().boundingBox())!;
  const selection = (await page.locator('.is-card > .task-selection-control').first().boundingBox())!;
  expect(Math.abs(card.y + card.height - selection.y - selection.height - 14)).toBeLessThan(1);
  expect(Math.abs(card.x + card.width - selection.x - selection.width - 14)).toBeLessThan(1);
  await page.screenshot({ path: info.outputPath('card-new-stickers.png'), animations: 'disabled' });
});
