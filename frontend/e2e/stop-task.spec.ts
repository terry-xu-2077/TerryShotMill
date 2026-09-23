import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("stop confirmation closes immediately and waits for terminal user-stopped state", async ({ page }) => {
  const project = await createProject(page, "停止交互");
  const task = await createTask(page, project.id, "运行任务");
  let stopped = false;
  let calls = 0;
  let finish!: () => void;
  const wait = new Promise<void>(resolve => { finish = resolve; });
  await page.route(`**/projects/${project.id}/workspace`, async route => {
    const body = await (await route.fetch()).json();
    Object.assign(body.tasks[0], {status: stopped ? "idle" : "running", videoGenerationStatus: stopped ? "idle" : "running", hasActiveVideoJob: !stopped, generationStatusNote: stopped ? "用户停止" : null});
    body.runtime.videoJobs = [{id:"running-job",taskId:task.id,title:"运行任务",state:stopped ? "cancelled" : "running",statusNote:stopped ? "用户停止" : null}];
    await route.fulfill({json:body});
  });
  await page.route(`**/projects/${project.id}/jobs/running-job/stop`, async route => {
    calls++;
    await wait;
    stopped = true;
    await route.fulfill({json:{accepted:true}});
  });
  await openProject(page, project.title);
  await page.locator('.task-list-row:not(.is-create)').first().click();
  await page.getByRole('button', {name:'停止任务', exact:true}).click();
  await page.getByRole('button', {name:'继续运行', exact:true}).click();
  expect(calls).toBe(0);
  await page.getByRole('button', {name:'停止任务', exact:true}).click();
  await page.getByRole('button', {name:'确认停止', exact:true}).click();
  await expect(page.getByRole('dialog', {name:'停止任务', exact:true})).toHaveCount(0);
  const pending = page.getByRole('button', {name:'正在停止', exact:true});
  await expect(pending).toBeDisabled();
  await expect(pending.locator('.task-stop-spinner')).toBeVisible();
  finish();
  await expect(page.getByRole('button', {name:'生成视频', exact:true})).toBeVisible();
  await expect(page.locator('.task-list-row:not(.is-create)').first()).toContainText('用户停止');
  expect(calls).toBe(1);
});
