import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("real step telemetry appears in inspector and text-free task light", async ({ page }) => {
  const project = await createProject(page, '生成进度');
  await createTask(page, project.id, '正在采样');
  await page.route(`**/projects/${project.id}/workspace`, async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.tasks[0].status = 'running';
    body.tasks[0].previewUrl = '/reference-image-should-not-be-cover.png';
    body.tasks[0].timing = {videoRunning:true, videoSeconds:120, measuredAt:new Date().toISOString(), generationProgress:{stage:'采样生成',step:4,total:10,percent:40,stageStartedAt:Date.now()/1000-100,measuredAt:Date.now()/1000-120,stageSeconds:100,remainingSeconds:150,stages:[{stage:'加载模型或素材',seconds:20}]}};
    await route.fulfill({json:body});
  });
  await openProject(page, project.title);
  const row = page.locator('.task-list-row:not(.is-create)').first();
  await expect(row.getByRole('progressbar')).toHaveAttribute('aria-valuenow','40');
  await expect(row.getByRole('progressbar')).toHaveText('');
  await expect(row.locator('.task-list-params')).toContainText('分辨率：1080P · 时长：6 秒');
  await expect(row).not.toContainText('角色穿过雨夜码头');
  expect(await row.evaluate(el => {
    const style = getComputedStyle(el, '::before');
    return [style.animationName, style.animationIterationCount, style.pointerEvents];
  })).toEqual(['task-running-breathe', 'infinite', 'none']);
  await expect(row.locator('.brand-placeholder')).toBeVisible();
  await row.click();
  const panel = page.getByRole('region', {name:'生成进度'});
  await expect(panel).toContainText('当前步骤 4 / 10');
  for (const light of [row.getByRole('progressbar'), panel.getByRole('progressbar')]) {
    const animation = await light.locator('span').evaluate(el => {
      const style = getComputedStyle(el, '::after');
      return [style.animationName, style.animationIterationCount];
    });
    expect(animation).toEqual(['task-progress-shimmer', 'infinite']);
    await expect(light).toHaveAttribute('aria-valuenow', '40');
  }
  await expect(panel).toContainText('本步骤预计剩余');
  await panel.getByText('已执行步骤').click();
  await expect(panel).toContainText('加载模型或素材');
  await page.getByRole('button', {name:'切换为卡片视图'}).click();
  await expect(page.locator('.task-card-item').first().getByRole('progressbar')).toHaveAttribute('aria-valuenow','40');
  await expect(page.locator('.task-card-item').first().locator(':scope > p')).toContainText('分辨率：1080P · 时长：6 秒');
  await expect(page.locator('.task-card-item').first()).not.toContainText('角色穿过雨夜码头');
});
