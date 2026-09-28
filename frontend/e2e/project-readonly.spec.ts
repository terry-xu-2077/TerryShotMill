import { expect, test } from "@playwright/test";
import { createProject, createTask, importImage } from "./helpers";

test("archived projects expose all result versions and assets without write controls", async ({ page }, info) => {
  const project = await createProject(page, "只读归档");
  const task = await createTask(page, project.id, "历史任务");
  await importImage(page, project.id, "历史图片");
  for (let i = 0; i < 2; i++) {
    const submitted = await page.request.post(`/api/v1/projects/${project.id}/tasks/${task.id}/generation`, { data: {} });
    expect(submitted.ok()).toBeTruthy();
    const job = await submitted.json();
    await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  }
  expect((await page.request.post(`/api/v1/projects/${project.id}/lifecycle`, { data: { action: "archive" } })).ok()).toBeTruthy();
  const writes: string[] = [];
  page.on("request", request => {
    if (request.url().includes(`/projects/${project.id}`) && ["POST", "PATCH", "DELETE"].includes(request.method())) writes.push(request.url());
  });
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "项目管理", exact: true }).click();
  const manager = page.getByRole("dialog", { name: "项目管理", exact: true });
  await manager.getByRole("button", { name: "已归档", exact: true }).click();
  await manager.locator(".project-lifecycle-row").filter({ hasText: project.title }).getByRole("button", { name: "查看", exact: true }).click();
  const browser = page.getByRole("dialog", { name: `只读项目 · ${project.title}` });
  await browser.getByRole("button", { name: "查看任务", exact: true }).click();
  const detail = page.getByRole("dialog", { name: "只读任务 · 历史任务" });
  await expect(detail.getByRole("button", { name: /^版本/ })).toHaveCount(2);
  const source = await detail.locator("video").getAttribute("src");
  await detail.getByRole("button", { name: /^版本/ }).nth(1).click();
  expect(await detail.locator("video").getAttribute("src")).not.toBe(source);
  const file = await page.request.get((await detail.getByRole("link", { name: "下载当前版本" }).getAttribute("href"))!);
  expect(file.ok()).toBeTruthy();
  await detail.evaluate(async el => { await Promise.all(el.getAnimations().map(animation => animation.finished)); });
  const bounds = await detail.boundingBox();
  await detail.getByRole("button", { name: "任务内容", exact: true }).click();
  expect(await detail.boundingBox()).toEqual(bounds);
  await expect(detail.getByText("角色穿过雨夜码头，抵达仓库入口", { exact: true })).toBeVisible();
  await expect(detail.getByRole("textbox")).toHaveCount(0);
  await expect(detail.getByRole("button", { name: /保存|生成视频|设为主结果/ })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("readonly-task.png") });
  await page.keyboard.press("Escape");
  await browser.getByRole("button", { name: "资产", exact: true }).click();
  await browser.getByRole("button", { name: "查看资产", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "只读资产 · 历史图片" }).getByRole("link", { name: "下载资产" })).toBeVisible();
  expect(writes).toEqual([]);
});
