import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("navigation protects drafts, recovers a failed save and keeps the editor open", async ({ page }, testInfo) => {
  const project = await createProject(page, "连续查看与草稿保护");
  const first = await createTask(page, project.id, "第一个镜头");
  const second = await createTask(page, project.id, "第二个镜头");
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").first().dblclick();
  const editor = page.getByRole("dialog", { name: /第一个镜头/ });
  const originalDialog = await editor.elementHandle();
  await editor.getByRole("tab", { name: /文本/ }).click();
  await page.keyboard.press("Alt+ArrowRight");
  await expect(page.getByRole("dialog", { name: /第二个镜头/ })).toBeVisible();
  expect(await originalDialog!.evaluate(element => element.isConnected)).toBe(true);
  await page.keyboard.press("Alt+ArrowLeft");
  await expect(editor).toBeVisible();
  await editor.getByRole("textbox", { name: "用户提示词", exact: true }).fill("要保留的动作修改");
  await editor.getByRole("button", { name: "下一个任务" }).click();
  const confirmation = page.getByRole("dialog", { name: "未保存的修改", exact: true });
  await expect(confirmation).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(confirmation).toHaveCount(0);
  await expect(editor.getByRole("textbox", { name: "用户提示词", exact: true })).toHaveValue("要保留的动作修改");
  await page.keyboard.press("Alt+ArrowRight");
  let failSave = true;
  await page.route(`**/projects/${project.id}/tasks/${first.id}`, route => {
    if (route.request().method() === "PATCH" && failSave) {
      failSave = false;
      return route.fulfill({ status: 503, json: { error: { code: "PROVIDER_UNAVAILABLE" } } });
    }
    return route.continue();
  });
  await confirmation.getByRole("button", { name: "保存并切换" }).click();
  await expect(confirmation.getByRole("alert")).toContainText("保存失败");
  await page.screenshot({ path: testInfo.outputPath("navigation-save-failure.png") });
  await confirmation.getByRole("button", { name: "保存并切换" }).click();
  const secondEditor = page.getByRole("dialog", { name: /第二个镜头/ });
  await expect(secondEditor).toBeVisible();
  expect(await originalDialog!.evaluate(element => element.isConnected)).toBe(true);
  const firstSaved = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${first.id}/editor`)).json();
  expect(firstSaved.userPrompt).toBe("要保留的动作修改");
  expect(firstSaved.promptReviewStatus).not.toBe("approved");
  await secondEditor.getByRole("tab", { name: /文本/ }).click();
  await secondEditor.getByRole("textbox", { name: "用户提示词", exact: true }).fill("放弃的临时内容");
  await page.keyboard.press("Alt+ArrowLeft");
  await confirmation.getByRole("button", { name: "放弃并切换" }).click();
  await expect(editor).toBeVisible();
  const secondSaved = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${second.id}/editor`)).json();
  expect(secondSaved.userPrompt).not.toContain("放弃的临时内容");
  await editor.getByRole("textbox", { name: "用户提示词", exact: true }).fill("快捷键保存的内容");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(editor).toHaveCount(0);
  const shortcutSaved = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${first.id}/editor`)).json();
  expect(shortcutSaved.userPrompt).toBe("快捷键保存的内容");
  expect(shortcutSaved.promptReviewStatus).not.toBe("approved");
});

test("task navigation never requires prompt approval", async ({ page }) => {
  const project = await createProject(page, "可选审核");
  const first = await createTask(page, project.id, "未审核镜头");
  await createTask(page, project.id, "下一个镜头");
  let approvals = 0;
  page.on("request", request => {
    if (request.url().endsWith('/prompt-review') && request.method() === 'POST') approvals++;
  });
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").first().dblclick();
  const editor = page.getByRole("dialog", { name: /未审核镜头/ });
  await expect(editor.getByRole("button", { name: "确认并下一个" })).toHaveCount(0);
  await editor.getByRole("button", { name: "下一个任务", exact: true }).click();
  await expect(page.getByRole("dialog", { name: /下一个镜头/ })).toBeVisible();
  expect(approvals).toBe(0);
  const saved = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${first.id}/editor`)).json();
  expect(saved.promptReviewStatus).not.toBe("approved");
});
